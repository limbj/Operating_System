import unittest

from scheduler import ProcessSpec, Simulator, run_simulation


class SchedulerTests(unittest.TestCase):
    def test_fcfs_p_core_waiting_time(self):
        result = run_simulation(
            [ProcessSpec(1, 0, 4), ProcessSpec(2, 0, 2)],
            [1, 0, 0, 0],
            "FCFS",
        )
        rows = {p.pid: p for p in result.process_results}
        self.assertEqual(rows[1].waiting_time, 0)
        self.assertEqual(rows[1].completion_time, 2)
        self.assertEqual(rows[2].waiting_time, 2)
        self.assertEqual(rows[2].completion_time, 3)

    def test_rr_preempts_on_fixed_quantum(self):
        result = run_simulation(
            [ProcessSpec(1, 0, 3), ProcessSpec(2, 0, 3)],
            [2, 0, 0, 0],
            "RR",
            time_quantum=2,
        )
        self.assertEqual(result.core_timelines[0], [1, 1, 2, 2, 1, 2])

    def test_drr_prefers_low_complexity_for_e_core(self):
        result = run_simulation(
            [
                ProcessSpec(1, 0, 8, "GPT 3.5", 3),
                ProcessSpec(2, 0, 8, "GPT 4", 8),
            ],
            [1, 1, 1, 2],
            "DRR",
        )
        self.assertEqual(result.core_timelines[3][0], 1)
        self.assertIn(2, [result.core_timelines[i][0] for i in (0, 1, 2)])

    def test_unused_e_core_has_no_power_usage(self):
        result = run_simulation(
            [ProcessSpec(1, 0, 8, "GPT 4", 8)],
            [1, 1, 1, 2],
            "DRR",
        )
        self.assertEqual(result.core_power_usage[3], 0.0)

    def test_drr_terminates_long_process_after_30_work_units(self):
        result = run_simulation(
            [ProcessSpec(1, 0, 35, "GPT 4", 20)],
            [1, 0, 0, 0],
            "DRR",
        )
        self.assertEqual(len(result.terminated), 1)
        self.assertEqual(result.terminated[0].executed_work, 30)
        self.assertEqual(result.terminated[0].status, "terminated")

    def test_core_limits_are_validated(self):
        with self.assertRaises(ValueError):
            Simulator([ProcessSpec(1, 0, 1)], [1, 1, 1, 1], "FCFS")
        with self.assertRaises(ValueError):
            Simulator([ProcessSpec(1, 0, 1)], [2, 2, 0, 0], "FCFS")


if __name__ == "__main__":
    unittest.main()
