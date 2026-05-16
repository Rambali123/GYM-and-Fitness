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
        self.cursor.execute("DELETE FROM subscriptions WHERE user_id IN (SELECT id FROM users WHERE email LIKE '%@test.com')")
        self.cursor.execute("DELETE FROM users WHERE email LIKE '%@test.com'")
        self.cursor.execute("DELETE FROM membership_plans WHERE name LIKE 'Test %'")
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

    def create_test_member(self):
        """Create a test member directly in the database and log in."""
        from werkzeug.security import generate_password_hash
        hashed = generate_password_hash('password123')
        self.cursor.execute(
            "INSERT INTO users (full_name, email, phone, password_hash, role) VALUES (%s,%s,%s,%s,%s)",
            ('Test Member', 'member@test.com', '1234567890', hashed, 'member')
        )
        self.db.commit()
        user_id = self.cursor.lastrowid
        # Log in via session
        with self.client.session_transaction() as sess:
            sess['user_id'] = user_id
            sess['user_name'] = 'Test Member'
            sess['role'] = 'member'
        return user_id


# ══════════════════════════════════════════════════════════════════════
#  SPRINT 2 TESTS — MEMBERSHIP PLANS & BILLING
# ══════════════════════════════════════════════════════════════════════

class TestSprint2MemberPlans(GymPulseBaseTest):
    """Test 01-04: Member-facing plans and subscription functionality."""

    def test_01_view_membership_plans(self):
        """Test 01: Member should see all available membership plans."""
        self.create_test_member()
        response = self.client.get('/plans')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Basic Monthly', response.data)
        self.assertIn(b'Standard Quarterly', response.data)
        self.assertIn(b'Premium Annual', response.data)
        print("TEST 01 PASSED: All membership plans displayed correctly.")

    def test_02_plans_show_euro_pricing(self):
        """Test 02: Plans should display prices in Euros."""
        self.create_test_member()
        response = self.client.get('/plans')
        self.assertIn(b'\xe2\x82\xac', response.data)  # € symbol in UTF-8
        print("TEST 02 PASSED: Plans display Euro pricing.")

    def test_03_subscribe_to_plan(self):
        """Test 03: Member should be able to subscribe to a plan."""
        user_id = self.create_test_member()

        self.cursor.execute("SELECT id FROM membership_plans LIMIT 1")
        plan_id = self.cursor.fetchone()['id']

        response = self.client.get(f'/subscribe/{plan_id}', follow_redirects=True)
        self.assertIn(b'Subscribed to', response.data)

        # Verify subscription in database
        self.cursor.execute("SELECT * FROM subscriptions WHERE user_id=%s", (user_id,))
        sub = self.cursor.fetchone()
        self.assertIsNotNone(sub)
        self.assertTrue(sub['paid'])
        self.assertEqual(sub['status'], 'active')
        print("TEST 03 PASSED: Subscription created with correct dates and paid status.")

    def test_04_subscribe_invalid_plan(self):
        """Test 04: Subscribing to a non-existent plan should show error."""
        self.create_test_member()
        response = self.client.get('/subscribe/9999', follow_redirects=True)
        self.assertIn(b'Plan not found', response.data)
        print("TEST 04 PASSED: Invalid plan subscription rejected.")


class TestSprint2AdminPlans(GymPulseBaseTest):
    """Test 05-08: Admin plan management."""

    def test_05_admin_add_plan(self):
        """Test 05: Admin should be able to add a new membership plan."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user_name'] = 'Admin'
            sess['role'] = 'admin'

        response = self.client.post('/admin/plans', data={
            'name': 'Test Weekly',
            'duration_days': '7',
            'price': '299.00',
            'description': 'Short term test plan'
        }, follow_redirects=True)
        self.assertIn(b'Plan added', response.data)
        self.assertIn(b'Test Weekly', response.data)
        print("TEST 05 PASSED: Admin added a new membership plan.")

    def test_06_admin_delete_plan(self):
        """Test 06: Admin should be able to delete a plan."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user_name'] = 'Admin'
            sess['role'] = 'admin'

        # Create a plan to delete
        self.cursor.execute(
            "INSERT INTO membership_plans (name, duration_days, price, description) VALUES (%s,%s,%s,%s)",
            ('Test Delete Plan', 7, 99.00, 'Temporary plan')
        )
        self.db.commit()
        plan_id = self.cursor.lastrowid

        response = self.client.get(f'/admin/plan/delete/{plan_id}', follow_redirects=True)
        self.assertIn(b'Plan deleted', response.data)

        self.cursor.execute("SELECT * FROM membership_plans WHERE id=%s", (plan_id,))
        self.assertIsNone(self.cursor.fetchone())
        print("TEST 06 PASSED: Admin deleted a membership plan.")

    def test_07_admin_view_all_plans(self):
        """Test 07: Admin plans page should display all existing plans."""
        with self.client.session_transaction() as sess:
            sess['user_id'] = 1
            sess['user_name'] = 'Admin'
            sess['role'] = 'admin'

        response = self.client.get('/admin/plans')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Basic Monthly', response.data)
        self.assertIn(b'Standard Quarterly', response.data)
        self.assertIn(b'Premium Annual', response.data)
        print("TEST 07 PASSED: Admin plans page displays all plans.")

    def test_08_new_plan_appears_for_members(self):
        """Test 08: A newly added plan should be visible to members."""
        # Admin adds a plan
        self.cursor.execute(
            "INSERT INTO membership_plans (name, duration_days, price, description) VALUES (%s,%s,%s,%s)",
            ('Test Premium Plus', 180, 4999.00, 'Six month premium access')
        )
        self.db.commit()

        # Member views plans
        self.create_test_member()
        response = self.client.get('/plans')
        self.assertIn(b'Test Premium Plus', response.data)
        print("TEST 08 PASSED: Newly added plan visible to members.")


# ── Run all tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    unittest.main(verbosity=2)