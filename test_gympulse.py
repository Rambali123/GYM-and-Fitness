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
        self.cursor.execute("DELETE FROM trainer_hours WHERE trainer_id IN (SELECT id FROM trainers WHERE phone='0000000000')")
        self.cursor.execute("DELETE FROM users WHERE email LIKE '%@test.com'")
        self.cursor.execute("DELETE FROM classes WHERE name LIKE 'Test %'")
        self.cursor.execute("DELETE FROM trainers WHERE phone='0000000000'")
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
        """Create and log in a test member, return user id."""
        self.register_test_user('Test Member', 'member@test.com', '1234567890', 'password123')
        self.login_user('member@test.com', 'password123')
        self.cursor.execute("SELECT id FROM users WHERE email='member@test.com'")
        return self.cursor.fetchone()['id']

    def create_test_trainer(self):
        """Insert a test trainer, return trainer id."""
        self.cursor.execute(
            "INSERT INTO trainers (full_name, specialisation, phone, hourly_rate) VALUES (%s,%s,%s,%s)",
            ('Test Trainer', 'Boxing', '0000000000', 25.00)
        )
        self.db.commit()
        return self.cursor.lastrowid

    def create_test_class(self, trainer_id=None):
        """Insert a test class, return class id."""
        self.cursor.execute(
            """INSERT INTO classes (name, description, trainer_id, schedule_date,
               start_time, end_time, max_capacity)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            ('Test HIIT Class', 'A test class', trainer_id, '2026-12-01', '09:00', '10:00', 20)
        )
        self.db.commit()
        return self.cursor.lastrowid


# ══════════════════════════════════════════════════════════════════════
#  SPRINT 3 TESTS — CLASS & ACTIVITY SCHEDULING
# ══════════════════════════════════════════════════════════════════════

class TestSprint3MemberClasses(GymPulseBaseTest):
    """Test 01-04: Member-facing class scheduling functionality."""

    def test_01_view_upcoming_classes(self):
        """Test 01: Member should see all upcoming classes."""
        self.create_test_member()
        self.create_test_class()
        response = self.client.get('/classes')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Test HIIT Class', response.data)
        print("TEST 01 PASSED: Upcoming classes displayed correctly.")

    def test_02_register_for_class(self):
        """Test 02: Member should be able to register for a class."""
        user_id = self.create_test_member()
        class_id = self.create_test_class()

        response = self.client.get(f'/class/register/{class_id}', follow_redirects=True)
        self.assertIn(b'Registered for class', response.data)

        # Verify in database
        self.cursor.execute(
            "SELECT * FROM class_registrations WHERE class_id=%s AND user_id=%s",
            (class_id, user_id)
        )
        self.assertIsNotNone(self.cursor.fetchone())
        print("TEST 02 PASSED: Member registered for class successfully.")

    def test_03_duplicate_registration_prevented(self):
        """Test 03: Duplicate class registration should be prevented."""
        self.create_test_member()
        class_id = self.create_test_class()

        self.client.get(f'/class/register/{class_id}', follow_redirects=True)
        response = self.client.get(f'/class/register/{class_id}', follow_redirects=True)
        self.assertIn(b'Already registered', response.data)

        # Verify only one record exists
        self.cursor.execute(
            "SELECT COUNT(*) AS cnt FROM class_registrations WHERE class_id=%s",
            (class_id,)
        )
        self.assertEqual(self.cursor.fetchone()['cnt'], 1)
        print("TEST 03 PASSED: Duplicate registration prevented.")

    def test_04_cancel_class_registration(self):
        """Test 04: Member should be able to cancel registration."""
        user_id = self.create_test_member()
        class_id = self.create_test_class()

        self.client.get(f'/class/register/{class_id}', follow_redirects=True)
        response = self.client.get(f'/class/cancel/{class_id}', follow_redirects=True)
        self.assertIn(b'Class registration cancelled', response.data)

        # Verify removed from database
        self.cursor.execute(
            "SELECT * FROM class_registrations WHERE class_id=%s AND user_id=%s",
            (class_id, user_id)
        )
        self.assertIsNone(self.cursor.fetchone())
        print("TEST 04 PASSED: Class registration cancelled successfully.")


class TestSprint3AdminClasses(GymPulseBaseTest):
    """Test 05: Admin class creation with trainer assignment."""

    def test_05_admin_create_class_with_trainer(self):
        """Test 05: Admin should be able to create a class and assign a trainer."""
        self.login_user('admin@gympulse.com', 'admin123')
        trainer_id = self.create_test_trainer()

        response = self.client.post('/admin/classes', data={
            'name': 'Test Yoga Session',
            'description': 'Admin created test class',
            'trainer_id': str(trainer_id),
            'schedule_date': '2026-12-15',
            'start_time': '10:00',
            'end_time': '11:00',
            'max_capacity': '15'
        }, follow_redirects=True)
        self.assertIn(b'Class added', response.data)
        self.assertIn(b'Test Yoga Session', response.data)

        # Verify trainer assignment in database
        self.cursor.execute("SELECT * FROM classes WHERE name='Test Yoga Session'")
        cls = self.cursor.fetchone()
        self.assertIsNotNone(cls)
        self.assertEqual(cls['trainer_id'], trainer_id)

        # Clean up
        self.cursor.execute("DELETE FROM classes WHERE name='Test Yoga Session'")
        self.db.commit()
        print("TEST 05 PASSED: Admin created class with trainer assigned.")


# ══════════════════════════════════════════════════════════════════════
#  SPRINT 4 TESTS — ASSIGN TRAINERS & TRACK HOURS
# ══════════════════════════════════════════════════════════════════════

class TestSprint4Trainers(GymPulseBaseTest):
    """Test 06 and 08: Trainer management."""

    def test_06_admin_add_trainer(self):
        """Test 06: Admin should be able to add a new trainer."""
        self.login_user('admin@gympulse.com', 'admin123')
        response = self.client.post('/admin/trainers', data={
            'full_name': 'Test Coach',
            'specialisation': 'CrossFit',
            'phone': '0000000000',
            'hourly_rate': '30.00'
        }, follow_redirects=True)
        self.assertIn(b'Trainer added', response.data)
        self.assertIn(b'Test Coach', response.data)

        # Verify in database
        self.cursor.execute("SELECT * FROM trainers WHERE full_name='Test Coach'")
        trainer = self.cursor.fetchone()
        self.assertIsNotNone(trainer)
        self.assertEqual(trainer['specialisation'], 'CrossFit')
        self.assertEqual(float(trainer['hourly_rate']), 30.00)
        print("TEST 06 PASSED: Admin added a new trainer.")

    def test_08_admin_delete_trainer_preserves_classes(self):
        """Test 08: Deleting a trainer should preserve assigned classes."""
        self.login_user('admin@gympulse.com', 'admin123')
        trainer_id = self.create_test_trainer()
        class_id = self.create_test_class(trainer_id=trainer_id)

        response = self.client.get(f'/admin/trainer/delete/{trainer_id}', follow_redirects=True)
        self.assertIn(b'Trainer removed', response.data)

        # Class should still exist with trainer_id set to NULL
        self.cursor.execute("SELECT * FROM classes WHERE id=%s", (class_id,))
        cls = self.cursor.fetchone()
        self.assertIsNotNone(cls)
        self.assertIsNone(cls['trainer_id'])

        # Trainer should be gone
        self.cursor.execute("SELECT * FROM trainers WHERE id=%s", (trainer_id,))
        self.assertIsNone(self.cursor.fetchone())
        print("TEST 08 PASSED: Trainer deleted, class preserved with NULL trainer.")


class TestSprint4Hours(GymPulseBaseTest):
    """Test 07: Hours tracking and pay calculation."""

    def test_07_log_trainer_hours(self):
        """Test 07: Admin should be able to log hours for a trainer."""
        self.login_user('admin@gympulse.com', 'admin123')
        trainer_id = self.create_test_trainer()
        class_id = self.create_test_class(trainer_id=trainer_id)

        response = self.client.post('/admin/hours', data={
            'trainer_id': str(trainer_id),
            'class_id': str(class_id),
            'hours_worked': '1.5',
            'log_date': '2026-12-01'
        }, follow_redirects=True)
        self.assertIn(b'Hours logged', response.data)

        # Verify in database
        self.cursor.execute(
            "SELECT * FROM trainer_hours WHERE trainer_id=%s AND class_id=%s",
            (trainer_id, class_id)
        )
        log = self.cursor.fetchone()
        self.assertIsNotNone(log)
        self.assertEqual(float(log['hours_worked']), 1.5)

        # Verify pay summary calculation
        self.cursor.execute("""
            SELECT SUM(th.hours_worked) AS total_hours,
                   SUM(th.hours_worked) * t.hourly_rate AS total_pay
            FROM trainer_hours th
            JOIN trainers t ON th.trainer_id = t.id
            WHERE th.trainer_id = %s
            GROUP BY t.id
        """, (trainer_id,))
        summary = self.cursor.fetchone()
        self.assertEqual(float(summary['total_hours']), 1.5)
        self.assertEqual(float(summary['total_pay']), 37.50)  # 1.5 * 25.00
        print("TEST 07 PASSED: Trainer hours logged and pay summary calculated correctly.")


# ── Run all tests ─────────────────────────────────────────────────────
if __name__ == '__main__':
    unittest.main(verbosity=2)