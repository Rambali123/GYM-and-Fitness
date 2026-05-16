CREATE DATABASE IF NOT EXISTS gympulse;
USE gympulse;

CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    phone VARCHAR(15),
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('member', 'admin') DEFAULT 'member',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE membership_plans (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    duration_days INT NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    description TEXT
);

CREATE TABLE subscriptions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    plan_id INT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    status ENUM('active', 'expired', 'cancelled') DEFAULT 'active',
    paid BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (plan_id) REFERENCES membership_plans(id)
);

CREATE TABLE trainers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    specialisation VARCHAR(100),
    phone VARCHAR(15),
    hourly_rate DECIMAL(8,2) DEFAULT 0.00
);

CREATE TABLE classes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    trainer_id INT,
    schedule_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    max_capacity INT DEFAULT 20,
    FOREIGN KEY (trainer_id) REFERENCES trainers(id)
);

CREATE TABLE class_registrations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    class_id INT NOT NULL,
    user_id INT NOT NULL,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (class_id) REFERENCES classes(id),
    FOREIGN KEY (user_id) REFERENCES users(id),
    UNIQUE(class_id, user_id)
);

CREATE TABLE trainer_hours (
    id INT AUTO_INCREMENT PRIMARY KEY,
    trainer_id INT NOT NULL,
    class_id INT NOT NULL,
    hours_worked DECIMAL(4,2) NOT NULL,
    log_date DATE NOT NULL,
    FOREIGN KEY (trainer_id) REFERENCES trainers(id),
    FOREIGN KEY (class_id) REFERENCES classes(id)
);

-- Default admin (password set by app on first run)
INSERT INTO users (full_name, email, phone, password_hash, role)
VALUES ('Admin', 'admin@gympulse.com', '9999999999',
        'pbkdf2:sha256:600000$placeholder$hash', 'admin');

-- Sample membership plans
INSERT INTO membership_plans (name, duration_days, price, description) VALUES
('Basic Monthly', 30, 999.00, 'Access to gym floor and basic equipment'),
('Standard Quarterly', 90, 2499.00, 'Gym access plus group classes'),
('Premium Annual', 365, 7999.00, 'Full access including personal training sessions');

