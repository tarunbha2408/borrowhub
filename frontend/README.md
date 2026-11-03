# BorrowHub — SVNIT Student Resource Sharing Frontend

A responsive frontend prototype for the SVNIT campus resource-sharing community.

## Student-first flow

1. A welcome screen displays “Welcome to SVNIT BorrowHub”.
2. The student sign-in / create-account interface opens automatically; sign-in is selected by default.
3. After a valid demo form submission, the modal closes and the homepage is shown.
4. Students can open **List an item** and add their own resource. The marketplace starts empty: no sample products or example loans are preloaded.

## Files

- `index.html` — page structure, welcome screen, authentication and listing dialogs
- `styles.css` — responsive design and sage/cream/terracotta theme
- `script.js` — client-side interactions and temporary demo state
- `assets/admin-building-outline.png` — SVNIT admin-building illustration used in the hero background

## Important demo limitations

- Authentication is **not real authentication**. The form currently validates the `@coed.svnit.ac.in` email format and demonstrates the post-login interface. Connect it to your backend API before using it with real student accounts.
- Listings added during a browser session are held in memory only. They disappear on refresh until the listing form is connected to the backend/database.
- Borrow requests, availability, messaging, payments, notifications, and loans are UI prototypes until connected to backend APIs.
- Do not collect or store real passwords in this frontend demo.

## Run locally

Open the folder in VS Code and use Live Server, or serve it with any static HTTP server. Keep `index.html`, `styles.css`, `script.js`, and the `assets` folder together.


## Demo authentication note
The sign-in and registration flow now checks accounts saved in this browser's localStorage. Register an account first, then sign in with the same email and password. A wrong password will keep the login dialog open and show an error. The welcome toast uses the name entered during registration. This is only a frontend demonstration and is not secure production authentication; accounts are not shared across browsers/devices and may be cleared by the user. For production, connect the form to a backend API that verifies password hashes securely. Run through localhost/Live Server so Web Crypto is available.
