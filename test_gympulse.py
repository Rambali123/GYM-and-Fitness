import unittest
import mysql.connector
from app import app


class GymPulseBaseTest(unittest.TestCase):
    """Base test class with shared setup and teardown."""

    def setUp(self):
        """Set up test client and clean test data."""
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret'
        self.client = app.test_client()
        self.db = mysql.connector.connect(
            host='localhost',
            user='root',
            password='12345',
            database='gympulse'
        )
        self.cursor = self.db.cursor(dictionary=True)
        self.clean_test_data()

    def tearDown(self):
        """Clean up after each test."""
        self.clean_test_data()
        self.cursor.close()
        self.db.close()

    def clean_test_data(self):
        """Remove test records from all tables."""
        self.cursor.execute("DELETE FROM class_registrations WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%@test.com')")
        self.cursor.execute("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%@test.com')")
        self.cursor.execute("DELETE FROM users WHERE email LIKE '%@test.com'")
        self.db.commit()

    def register_test_user(self, name, email, phone, password):
        """Helper to register a user via the registration form."""
        return self.client.post('/register', data={
            'full_name': name,
            'email': email,
            'phone': phone,
            'password': password
        }, follow_redirects=True)

    def login_user(self, email, password):
        """Helper to log in a user."""
        return self.client.post('/login', data={
            'email': email,
            'password': password
        }, follow_redirects=True)


# ══════════════════════════════════════════════════════════════════════
#  SPRINT 1 TESTS — REGISTER & LOGIN
# ══════════════════════════════════════════════════════════════════════

class TestSprint1Registration(GymPulseBaseTest):
    """Test 01-03: User registration functionality."""

    def test_01_successful_registration(self):
        """Test 01: A new user should be able to register an account."""
        response = self.register_test_user(
            'John Smith', 'john@test.com', '07412345678', 'secure123'
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Registration successful', response.data)

        # Verify record exists in database
        self.cursor.execute("SELECT * FROM users WHERE email='john@test.com'")
        user = self.cursor.fetchone()
        self.assertIsNotNone(user)
        self.assertEqual(user['full_name'], 'John Smith')
        self.assertEqual(user['role'], 'member')
        self.assertNotEqual(user['password_hash'], 'secure123')
        print("TEST 01 PASSED: New user registered successfully.")

    def test_02_duplicate_email_rejected(self):
        """Test 02: Registration with an existing email should be rejected."""
        self.register_test_user('First User', 'duplicate@test.com', '1111111111', 'pass123')
        response = self.register_test_user('Second User', 'duplicate@test.com', '2222222222', 'pass456')
        self.assertIn(b'Email already registered', response.data)

        # Verify only one record exists
        self.cursor.execute("SELECT COUNT(*) AS cnt FROM users WHERE email='duplicate@test.com'")
        count = self.cursor.fetchone()['cnt']
        self.assertEqual(count, 1)
        print("TEST 02 PASSED: Duplicate email registration rejected.")

    def test_03_password_hashed_in_database(self):
        """Test 03: Passwords should be stored as hashes, not plain text."""
        self.register_test_user('Hash Test', 'hash@test.com', '3333333333', 'mypassword')
        self.cursor.execute("SELECT password_hash FROM users WHERE email='hash@test.com'")
        row = self.cursor.fetchone()
        self.assertTrue(row['password_hash'].startswith('pbkdf2:sha256'))
        self.assertNotIn('mypassword', row['password_hash'])
        print("TEST 03 PASSED: Password stored as PBKDF2-SHA256 hash.")


class TestSprint1Login(GymPulseBaseTest):
    """Test 04-07: User login and session functionality."""

    def test_04_successful_member_login(self):
        """Test 04: A registered member should be able to log in."""
        self.register_test_user('Jane Doe', 'jane@test.com', '4444444444', 'pass123')
        response = self.login_user('jane@test.com', 'pass123')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Welcome', response.data)
        print("TEST 04 PASSED: Member logged in and redirected to dashboard.")

    def test_05_invalid_password_rejected(self):
        """Test 05: Incorrect password should show an error."""
        self.register_test_user('Wrong Pass', 'wrong@test.com', '5555555555', 'correct123')
        response = self.login_user('wrong@test.com', 'wrongpassword')
        self.assertIn(b'Invalid email or password', response.data)
        print("TEST 05 PASSED: Invalid password rejected with error message.")

    def test_06_admin_redirected_to_admin_dashboard(self):
        """Test 06: Admin should be redirected to admin dashboard."""
        response = self.login_user('admin@gympulse.com', 'admin123')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Admin Dashboard', response.data)
        print("TEST 06 PASSED: Admin redirected to admin dashboard.")

    def test_07_logout_clears_session(self):
        """Test 07: Logging out should clear the session."""
        self.register_test_user('Logout Test', 'logout@test.com', '6666666666', 'pass123')
        self.login_user('logout@test.com', 'pass123')
        response = self.client.get('/logout', follow_redirects=True)
        self.assertIn(b'Logged out', response.data)

        # Trying to access dashboard should redirect to login
        response = self.client.get('/dashboard', follow_redirects=True)
        self.assertIn(b'Login to GymPulse', response.data)
        print("TEST 07 PASSED: Logout cleared session and redirected to login.")


class TestSprint1Profile(GymPulseBaseTest):
    """Test 08: Profile update functionality."""

    def test_08_update_profile(self):
        """Test 08: Member should be able to update name and phone."""
        self.register_test_user('Old Name', 'profile@test.com', '7777777777', 'pass123')
        self.login_user('profile@test.com', 'pass123')

        response = self.client.post('/profile', data={
            'full_name': 'New Name',
            'phone': '9999999999'
        }, follow_redirects=True)
        self.assertIn(b'Profile updated', response.data)

        # Verify in database
        self.cursor.execute("SELECT * FROM users WHERE email='profile@test.com'")
        user = self.cursor.fetchone()
        self.assertEqual(user['full_name'], 'New Name')
        self.assertEqual(user['phone'], '9999999999')
        print("TEST 08 PASSED: Profile name and phone updated successfully.")


# ── Run all tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    unittest.main(verbosity=2)