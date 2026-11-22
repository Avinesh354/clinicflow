import threading
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone

from clinic import services
from clinic.models import Appointment, AppointmentSlot, Doctor, Patient, QueueEntry, Specialty


def run_parallel(fn, n):
    """Run fn(i) in n threads released simultaneously; return (results, errors)."""
    barrier, results, errors = threading.Barrier(n), [], []

    def worker(i):
        try:
            barrier.wait()
            results.append(fn(i))
        except Exception as e:  # collected and inspected by the test
            errors.append(e)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    return results, errors


class ClinicBase(TransactionTestCase):
    def setUp(self):
        u = get_user_model().objects.create_user("doc1")
        self.doctor = Doctor.objects.create(user=u, specialty=Specialty.objects.create(name="GP"))
        self.patients = [Patient.objects.create(name=f"P{i}") for i in range(10)]
        # on the booking grid in clinic-local time
        self.start = timezone.localtime(timezone.now() + timedelta(days=1)).replace(
            minute=0, second=0, microsecond=0)


class BookingTests(ClinicBase):
    def test_parallel_bookings_same_slot_exactly_one_wins(self):
        end = self.start + timedelta(minutes=20)
        results, errors = run_parallel(
            lambda i: services.book_appointment(doctor=self.doctor, patient=self.patients[i],
                                                start=self.start, end=end), 10)
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 9)
        self.assertTrue(all(isinstance(e, services.SlotTaken) for e in errors))
        self.assertEqual(Appointment.objects.count(), 1)

    def test_multi_slot_overlap_rejected(self):
        services.book_appointment(doctor=self.doctor, patient=self.patients[0],
                                  start=self.start, end=self.start + timedelta(minutes=40))
        # starts inside the first appointment's second slot
        with self.assertRaises(services.SlotTaken):
            services.book_appointment(doctor=self.doctor, patient=self.patients[1],
                                      start=self.start + timedelta(minutes=20),
                                      end=self.start + timedelta(minutes=40))
        # starts in a free slot but runs into the booked one
        with self.assertRaises(services.SlotTaken):
            services.book_appointment(doctor=self.doctor, patient=self.patients[2],
                                      start=self.start - timedelta(minutes=20),
                                      end=self.start + timedelta(minutes=20))
        self.assertEqual(Appointment.objects.count(), 1)  # failed bookings left nothing behind

    def test_parallel_overlapping_multi_slot_one_wins_and_no_partial_rows(self):
        def book(i):  # two different 40-min windows that share one slot
            s = self.start + timedelta(minutes=20 * i)
            return services.book_appointment(doctor=self.doctor, patient=self.patients[i],
                                             start=s, end=s + timedelta(minutes=40))
        results, errors = run_parallel(book, 2)
        self.assertEqual(len(results), 1)
        self.assertTrue(all(isinstance(e, services.SlotTaken) for e in errors), errors)
        self.assertEqual(Appointment.objects.count(), 1)
        self.assertEqual(AppointmentSlot.objects.count(), 2)

    def test_off_grid_and_bad_duration_rejected(self):
        for start, mins in [(self.start + timedelta(minutes=15), 20), (self.start, 25), (self.start, 0)]:
            with self.assertRaises(services.InvalidSlot):
                services.book_appointment(doctor=self.doctor, patient=self.patients[0],
                                          start=start, end=start + timedelta(minutes=mins))

    def test_adjacent_allowed_and_cancel_frees_slot(self):
        a = services.book_appointment(doctor=self.doctor, patient=self.patients[0],
                                      start=self.start, end=self.start + timedelta(minutes=20))
        services.book_appointment(doctor=self.doctor, patient=self.patients[1],
                                  start=self.start + timedelta(minutes=20),
                                  end=self.start + timedelta(minutes=40))
        services.cancel_appointment(a.pk)
        self.assertEqual(AppointmentSlot.objects.filter(appointment=a).count(), 0)
        services.book_appointment(doctor=self.doctor, patient=self.patients[2],
                                  start=self.start, end=self.start + timedelta(minutes=20))


class QueueTests(ClinicBase):
    def _appts(self, n):
        return [services.book_appointment(doctor=self.doctor, patient=self.patients[i],
                                          start=self.start + timedelta(minutes=20 * i),
                                          end=self.start + timedelta(minutes=20 * (i + 1)))
                for i in range(n)]

    def test_concurrent_check_ins_get_unique_sequential_tokens(self):
        appts = self._appts(8)
        results, errors = run_parallel(lambda i: services.check_in(appts[i]), 8)
        self.assertEqual(errors, [])
        self.assertEqual(sorted(e.token_number for e in results), list(range(1, 9)))

    def test_only_one_patient_in_consultation(self):
        appts = self._appts(5)
        entries = [services.check_in(a) for a in appts]
        results, errors = run_parallel(lambda i: services.start_consultation(entries[i].pk), 5)
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 4)
        self.assertEqual(QueueEntry.objects.filter(status="in_consultation").count(), 1)

    def test_snapshot_and_position(self):
        appts = self._appts(4)
        entries = [services.check_in(a) for a in appts]
        services.start_consultation(entries[0].pk)
        snap = services.doctor_queue_snapshot(self.doctor.pk, entries[0].queue_date)
        self.assertEqual(snap["now_serving"], 1)
        self.assertEqual(snap["waiting_count"], 3)
        pos = services.patient_position(entries[3])
        self.assertEqual(pos["ahead_of_you"], 2)
        self.assertEqual(pos["position"], 3)
        services.finish_consultation(entries[0].pk)
        self.assertIsNone(services.doctor_queue_snapshot(self.doctor.pk, entries[0].queue_date)["now_serving"])
        self.assertEqual(Appointment.objects.get(pk=appts[0].pk).status, "completed")
