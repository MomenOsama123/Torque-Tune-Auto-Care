-- ============================
-- seed.sql
-- ============================

-- Users
INSERT INTO Users (name, email, role) VALUES ('Mostafa Adel', 'mostafa@autofix.com', 'manager');
INSERT INTO Users (name, email, role) VALUES ('Ahmed Samir', 'ahmed@autofix.com', 'technician');

-- Categories
INSERT INTO Categories (name, description) VALUES
('Brakes', 'Brake pads, discs, calipers and related hardware'),
('Engine', 'Engine internals, gaskets, belts, filters'),
('Electrical', 'Batteries, sensors, wiring, fuses'),
('Suspension', 'Shocks, struts, springs, bushings');

-- Suppliers
INSERT INTO Suppliers (name, phone, email, address) VALUES
('CairoParts Trading', '+20-2-25551234', 'sales@cairoparts.com', '12 Industrial Zone, Cairo'),
('Delta Auto Supply', '+20-2-25559876', 'contact@deltaauto.com', '45 Ring Road, Giza'),
('NorthCoast Distributors', '+20-3-4881122', 'info@northcoastparts.com', '7 Port Street, Alexandria');

-- SpareParts
INSERT INTO SpareParts (part_name, part_number, category_id, supplier_id, quantity, price, location, minimum_stock, status) VALUES
('Brake Pad Set - Front', 'BP-1023', 1, 1, 12, 450.00, 'Shelf A3', 5, 'active'),
('Brake Pad Set - Rear',  'BP-1024', 1, 1, 30, 380.00, 'Shelf A4', 5, 'active'),
('Brake Disc - Standard', 'BD-2050', 1, 2, 0,  620.00, 'Shelf A6', 4, 'active'),
('Timing Belt Kit',       'TB-3010', 2, 2, 3,  950.00, 'Shelf B1', 6, 'active'),
('Oil Filter - Standard', 'OF-3300', 2, 1, 80, 60.00,  'Shelf B2', 15, 'active'),
('Car Battery 60Ah',      'BT-4400', 3, 3, 10, 1500.00,'Shelf C1', 3, 'active'),
('Old Model Alternator',  'AL-9000', 3, 3, 2,  1200.00,'Shelf C5', 2, 'discontinued'),
('Shock Absorber - Front','SA-5010', 4, 2, 18, 700.00, 'Shelf D1', 5, 'active');

-- AlternativeParts
INSERT INTO AlternativeParts (part_id, alternative_part_id) VALUES
(5, 6),
(6, 5);

-- InventoryLogs
INSERT INTO InventoryLogs (part_id, user_id, old_quantity, new_quantity, action, reason) VALUES
(1, 1, 20, 12, 'decrease', 'Used in repair job #4521 - front brake replacement'),
(6, 1, 5, 10, 'increase', 'New stock received from CairoParts Trading'),
(3, 1, 8, 0, 'decrease', 'Emergency repair - brake disc stock depleted'),
(4, 2, 6, 3, 'decrease', 'Timing belt kit used in scheduled maintenance');
