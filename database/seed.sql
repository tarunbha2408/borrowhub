-- BorrowHub Default Seed Data for SVNIT Campus
USE borrowhub;

-- 1. CATEGORIES
INSERT IGNORE INTO category (category_id, category_name, category_description) VALUES
 (1, 'Books',               'Textbooks, reference books and novels'),
 (2, 'Electronics',         'Calculators, Arduino kits, chargers, cables and gadgets'),
 (3, 'Lab Equipment',       'Lab coats, drafters, multimeters, kits and instruments'),
 (4, 'Sports',              'Bats, rackets, balls and fitness gear'),
 (5, 'Tools',               'Hand tools, soldering irons and hardware'),
 (6, 'Stationery',          'Pens, drawing sheets and project supplies'),
 (7, 'Musical Instruments', 'Guitars, keyboards and accessories'),
 (8, 'Others',              'Miscellaneous campus utility items');

-- 2. PICKUP LOCATIONS
INSERT IGNORE INTO pickup_location (location_id, name, description) VALUES
 (1, 'Bhabha Bhavan',            'Bhabha Bhavan Hostel Main Gate / Reception'),
 (2, 'Gajjar Bhavan',            'Gajjar Bhavan Hostel Main Gate / Reception'),
 (3, 'Swami Vivekanand Bhavan',  'SVB Hostel Main Entrance'),
 (4, 'Mother Teresa Bhavan',     'MTB Hostel Main Entrance'),
 (5, 'CSE Department',           'Computer Science & Engineering Ground Floor Lobby'),
 (6, 'Central Library',          'SVNIT Central Library Entrance'),
 (7, 'Main Gate / SAC',          'Student Activity Centre / Main Gate Security Cabin');

-- 3. PRE-CONFIGURED USERS (Password for all accounts is: Svnit@2026!)
INSERT INTO app_user (user_id, roll_number, full_name, svnit_email, phone, hostel_or_dept, password_hash, role, is_verified, is_active)
VALUES
 (1, 'U23CS001', 'Aarav Patel', 'u23cs001@svnit.ac.in', '+919876543210', 'Bhabha Bhavan', '$2b$12$C.40z4x3335YiOBR9R0DT.vqOyhZFIriHdNpiYhAKT40PYUF52Th2', 'STUDENT', 1, 1),
 (2, 'U23CS002', 'Priya Shah', 'u23cs002@svnit.ac.in', '+919876543211', 'Mother Teresa Bhavan', '$2b$12$C.40z4x3335YiOBR9R0DT.vqOyhZFIriHdNpiYhAKT40PYUF52Th2', 'STUDENT', 1, 1),
 (3, 'U23CS003', 'Rohan Mehta', 'u23cs003@svnit.ac.in', '+919876543212', 'Gajjar Bhavan', '$2b$12$C.40z4x3335YiOBR9R0DT.vqOyhZFIriHdNpiYhAKT40PYUF52Th2', 'STUDENT', 1, 1),
 (4, 'ADMIN001', 'Campus Administrator', 'admin@svnit.ac.in', '+919876543299', 'Central Administration', '$2b$12$C.40z4x3335YiOBR9R0DT.vqOyhZFIriHdNpiYhAKT40PYUF52Th2', 'ADMIN', 1, 1),
 (14, 'U22CS001', 'Priya Sharma', 'priya@coed.svnit.ac.in', '+919876543220', 'Mother Teresa Bhavan', '$2b$12$C.40z4x3335YiOBR9R0DT.vqOyhZFIriHdNpiYhAKT40PYUF52Th2', 'STUDENT', 1, 1),
 (15, 'U22CS014', 'Aarav Patel', 'aarav@coed.svnit.ac.in', '+919876543221', 'Bhabha Bhavan', '$2b$12$C.40z4x3335YiOBR9R0DT.vqOyhZFIriHdNpiYhAKT40PYUF52Th2', 'STUDENT', 1, 1),
 (16, 'U22EE028', 'Rohit Verma', 'rohit@coed.svnit.ac.in', '+919876543222', 'Swami Vivekananda Bhavan', '$2b$12$C.40z4x3335YiOBR9R0DT.vqOyhZFIriHdNpiYhAKT40PYUF52Th2', 'STUDENT', 1, 1)
ON DUPLICATE KEY UPDATE
 password_hash = VALUES(password_hash),
 is_verified = 1,
 is_active = 1,
 role = VALUES(role);

-- 4. PRE-CONFIGURED ACTIVE ITEMS
INSERT INTO item (item_id, owner_id, category_id, location_id, title, description, item_condition, deposit_amount, daily_fee, max_borrow_days, listing_status)
VALUES
 (1, 1, 2, 1, 'Casio FX-991EX Classwiz Scientific Calculator', 'Ideal for engineering mathematics, matrices, equations and scientific computations. Clean condition with solar cell.', 'NEW', 300.00, 15.00, 7, 'ACTIVE'),
 (2, 1, 2, 5, 'Arduino Uno R4 WiFi Kit with Sensor Modules', 'Original Arduino R4 with ESP32-S3 WiFi, breadboard, jumper wires, ultrasonic, temperature and OLED modules.', 'GOOD', 500.00, 50.00, 14, 'ACTIVE'),
 (3, 2, 3, 4, 'Omega Mini Drafter & Engineering Sheet Clips', 'Complete engineering graphics drawing kit with scale clamp, protractor arm and board clips in original bag.', 'GOOD', 400.00, 20.00, 10, 'ACTIVE'),
 (4, 3, 4, 2, 'Yonex Carbonex 8000 Plus Badminton Racket', 'High modulus graphite badminton racket with full cover and new BG-65 strings. Grip newly replaced.', 'GOOD', 350.00, 25.00, 5, 'ACTIVE'),
 (5, 2, 1, 6, 'Computer Organization & Architecture (10th Ed)', 'Hardcover textbook by William Stallings. Essential for 3rd semester CSE/ECE coursework. Highlighting in pencil only.', 'FAIR', 200.00, 10.00, 21, 'ACTIVE'),
 (37, 14, 2, 4, 'Casio FX-991EX Scientific Calculator & Drafter', 'Original Casio Classwiz fx-991EX and mini drafter in excellent condition. Ideal for exams.', 'GOOD', 300.00, 20.00, 10, 'ACTIVE')
ON DUPLICATE KEY UPDATE
 title = VALUES(title),
 daily_fee = VALUES(daily_fee),
 deposit_amount = VALUES(deposit_amount),
 listing_status = 'ACTIVE';

-- 5. item IMAGES (Fallback high-quality campus photos)
INSERT IGNORE INTO item_image (image_id, item_id, image_url, sort_order, is_primary) VALUES
 (1, 1, 'https://images.unsplash.com/photo-1594980596870-8aa52a78d8cd?w=600&auto=format&fit=crop&q=80', 0, 1),
 (2, 2, 'https://images.unsplash.com/photo-1518770660439-4636190af475?w=600&auto=format&fit=crop&q=80', 0, 1),
 (3, 3, 'https://images.unsplash.com/photo-1581092335397-9583fe92d232?w=600&auto=format&fit=crop&q=80', 0, 1),
 (4, 4, 'https://images.unsplash.com/photo-1626224583764-f87db24ac4ea?w=600&auto=format&fit=crop&q=80', 0, 1),
 (5, 5, 'https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?w=600&auto=format&fit=crop&q=80', 0, 1),
 (37, 37, 'https://images.unsplash.com/photo-1594980596870-8aa52a78d8cd?w=600&auto=format&fit=crop&q=80', 0, 1);
