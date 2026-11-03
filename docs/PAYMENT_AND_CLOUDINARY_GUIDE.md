# BorrowHub — Payment Gateway & Cloudinary Integration Guide

This guide details the configuration and operations for **Razorpay Standard Checkout** and **Cloudinary Image Storage** inside BorrowHub.

---

## 1. Razorpay Payment Gateway Integration

BorrowHub uses Razorpay for rental payments, refundable security deposit custody, and late/damage fee deductions.

### 1.1 Configuration (`backend/.env`)
Set the following environment variables:

```env
# Razorpay Credentials (Get from https://dashboard.razorpay.com/app/keys)
RAZORPAY_KEY_ID=rzp_test_your_key_id
RAZORPAY_KEY_SECRET=your_key_secret_here
RAZORPAY_WEBHOOK_SECRET=your_webhook_secret_here
```

### 1.2 Architecture & Flow
1. **Order Creation (`POST /api/payments/create-order`):**
   - The backend checks the loan status and fetches `agreed_total_fee` or `agreed_deposit`.
   - The amount is converted to Indian Paisa subunits ($1\text{ INR} = 100\text{ paise}$).
   - An order is registered with Razorpay using `razorpay.Client.order.create()`.
   - A `PAYMENT` row is recorded in MySQL with status `PENDING`.
   - Returns `{ order_id, amount_subunits, currency: "INR", key_id }`.

2. **Client-Side Checkout:**
   - In production, the frontend invokes Razorpay's standard checkout script:
     ```javascript
     const rzp = new Razorpay({
       key: order.key_id,
       amount: order.amount_subunits,
       currency: "INR",
       name: "BorrowHub SVNIT",
       description: "Campus Resource Rental & Security Deposit",
       order_id: order.order_id,
       handler: function(response) {
         // Send response.razorpay_order_id, razorpay_payment_id, razorpay_signature to backend
         verifyPayment(response);
       }
     });
     rzp.open();
     ```
   - In Test Mode development, the modal also offers simulated test payments and peer cash confirmations.

3. **Server-Side Signature Verification (`POST /api/payments/verify`):**
   - The backend verifies HMAC-SHA256 signature using `client.utility.verify_payment_signature()`:
     $$\text{signature} = \text{HMAC-SHA256}(\text{order\_id} + "|" + \text{payment\_id}, \text{RAZORPAY\_KEY\_SECRET})$$
   - Once verified, the payment status transitions to `COMPLETED` and the deposit status updates to `HELD`.

4. **Security Deposit Settlement & Refunds (`POST /api/loans/{id}/settle-deposit`):**
   - When the item is returned on time without damage, the security deposit is refunded to the borrower.
   - If damage or late return occurred, deductions are applied, and the net refundable amount is issued via Razorpay's refund API (`client.payment.refund()`).

---

## 2. Cloudinary Media Storage Integration

BorrowHub stores item photos on Cloudinary's global Content Delivery Network (CDN), preventing heavy binary blobs from bloating the MySQL database.

### 2.1 Configuration (`backend/.env`)
Set your Cloudinary API credentials:

```env
# Cloudinary Credentials (Get from https://console.cloudinary.com/)
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret
```

### 2.2 Server-Side Upload Flow (`POST /api/upload`)
- Students select up to 5 photographs in the listing form.
- The files are posted to `/api/upload` as multipart form data.
- The service (`backend/app/services/cloudinary_service.py`):
  1. Validates that the file size is $\le 5\text{ MB}$.
  2. Validates that the MIME type is in `{'image/jpeg', 'image/png', 'image/webp'}`.
  3. Uploads the image to Cloudinary under folder `borrowhub/listings` with automatic optimization and responsive quality.
  4. Returns the secure HTTPS URL (`https://res.cloudinary.com/...`).
- When Cloudinary credentials are not configured in local development, the service smoothly falls back to storing images in `backend/static/uploads/` and serving them at `http://localhost:8000/uploads/...`.
- Only the image URLs and metadata are stored in MySQL table `ITEM_IMAGE`.
