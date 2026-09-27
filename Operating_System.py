"""Command-line entry point for the processor scheduling simulator.

For the full graphical interface, run ``python ui.py``.
"""

from scheduler import ProcessSpec, run_simulation


def main():
    processes = [
        ProcessSpec(1, 1, 6, "GPT 3.5", 6),
        ProcessSpec(2, 12, 20, "GPT 4", 10),
        ProcessSpec(3, 7, 3, "GPT 3.5", 3),
        ProcessSpec(4, 16, 16, "GPT 4", 8),
        ProcessSpec(5, 8, 18, "GPT 4", 9),
        ProcessSpec(6, 2, 8, "GPT 3.5", 8),
        ProcessSpec(7, 15, 6, "GPT 4", 3),
        ProcessSpec(8, 7, 2, "GPT 3.5", 2),
        ProcessSpec(9, 3, 1, "GPT 3.5", 1),
        ProcessSpec(10, 0, 14, "GPT 4", 7),
        ProcessSpec(11, 1, 12, "GPT 4", 6),
        ProcessSpec(12, 13, 9, "GPT 3.5", 9),
        ProcessSpec(13, 5, 24, "GPT 4", 12),
        ProcessSpec(14, 4, 11, "GPT 3.5", 11),
        ProcessSpec(15, 11, 10, "GPT 4", 5),
    ]

    result = run_simulation(processes, [1, 1, 1, 2], "DRR")

    print("PID | AT | BT | RUN | WT | TT | NTT | CT | STATUS")
    for row in sorted(result.process_results, key=lambda item: item.pid):
        print(
            f"{row.pid:>3} | {row.arrival_time:>2} | {row.burst_time:>2} | "
            f"{row.run_time:>3} | {row.waiting_time:>2} | {row.turnaround_time:>2} | "
            f"{row.normalized_turnaround_time:>4.2f} | {row.completion_time:>2} | {row.status}"
        )

    print()
    print(f"Average WT  : {result.average_waiting_time}")
    print(f"Average NTT : {result.average_normalized_turnaround_time}")
    print(f"P-Core power: {result.p_core_power_usage} W")
    print(f"E-Core power: {result.e_core_power_usage} W")
    print(f"Total power : {result.total_power_usage} W")
    print(f"Duration    : {result.duration} sec")


if __name__ == "__main__":
    main()
