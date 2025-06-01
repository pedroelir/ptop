import curses
import os
import time
import pwd

__version__ = "0.1.0"

def get_uptime():
    with open("/proc/uptime", "r") as f:
        return float(f.readline().split()[0])

def get_total_memory():
    with open("/proc/meminfo", "r") as f:
        for line in f:
            if line.startswith("MemTotal:"):
                return int(line.split()[1])  # kB
    return 1

def get_memory_info():
    mem = {}
    with open("/proc/meminfo", "r") as f:
        for line in f:
            parts = line.split()
            if parts[0] in ["MemTotal:", "MemFree:", "Buffers:", "Cached:"]:
                mem[parts[0][:-1]] = int(parts[1])
    total = mem.get("MemTotal", 1)
    free = mem.get("MemFree", 0) + mem.get("Buffers", 0) + mem.get("Cached", 0)
    used = total - free
    return used, free, total

def get_load_average():
    with open("/proc/loadavg", "r") as f:
        return f.read().strip()

def read_processes():
    processes = []
    total_memory = get_total_memory()
    uptime = get_uptime()
    hertz = os.sysconf(os.sysconf_names['SC_CLK_TCK'])

    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            with open(f"/proc/{pid}/stat", "r") as f:
                stat = f.read().split()
            with open(f"/proc/{pid}/cmdline", "r") as f:
                cmdline = f.read().replace('\x00', ' ').strip()
            if not cmdline:
                cmdline = stat[1].strip("()")

            with open(f"/proc/{pid}/status", "r") as f:
                status = f.read()
            uid_line = next(line for line in status.splitlines() if line.startswith("Uid:"))
            uid = int(uid_line.split()[1])
            user = pwd.getpwuid(uid).pw_name

            utime = int(stat[13])
            stime = int(stat[14])
            start_time = int(stat[21])
            total_time = utime + stime
            seconds = uptime - (start_time / hertz)
            cpu_usage = 100 * ((total_time / hertz) / seconds) if seconds > 0 else 0

            with open(f"/proc/{pid}/status", "r") as f:
                mem_line = next((line for line in f if line.startswith("VmRSS:")), None)
                mem_kb = int(mem_line.split()[1]) if mem_line else 0
                mem_percent = (mem_kb / total_memory) * 100

            processes.append({
                'pid': int(pid),
                'user': user,
                'cpu': cpu_usage,
                'mem': mem_percent,
                'cmd': cmdline
            })
        except Exception:
            continue
    return sorted(processes, key=lambda p: p['cpu'], reverse=True)

def get_cpu_usage(prev):
    with open("/proc/stat", "r") as f:
        line = f.readline()
    parts = list(map(int, line.split()[1:8]))  # user, nice, system, idle, iowait, irq, softirq
    total = sum(parts)
    idle = parts[3] + parts[4]
    if prev:
        prev_total, prev_idle = prev
        delta_total = total - prev_total
        delta_idle = idle - prev_idle
        usage = 100 * (1 - delta_idle / delta_total) if delta_total > 0 else 0
    else:
        usage = 0
    return usage, (total, idle)

def draw_process_page(stdscr, offset, height, width):
    stdscr.addstr(0, 0, " PID   USER       CPU%   MEM%   COMMAND", curses.A_BOLD)
    processes = read_processes()
    for idx, proc in enumerate(processes[offset:offset + height - 2]):
        line = f"{proc['pid']:5}  {proc['user'][:10]:10}  {proc['cpu']:5.1f}  {proc['mem']:5.1f}  {proc['cmd'][:width - 35]}"
        stdscr.addstr(idx + 1, 0, line)

def draw_summary_page(stdscr):
    used, free, total = get_memory_info()
    load = get_load_average()
    uptime = get_uptime()
    cpu_count = os.cpu_count()

    stdscr.addstr(0, 0, "System Summary", curses.A_BOLD)
    stdscr.addstr(2, 2, f"Uptime: {uptime:.0f} seconds")
    stdscr.addstr(3, 2, f"Memory: {used} KB used / {total} KB total")
    stdscr.addstr(4, 2, f"Load Avg: {load}")
    stdscr.addstr(5, 2, f"CPU Cores: {cpu_count}")

def draw_cpu_graph_page(stdscr, cpu_history):
    stdscr.addstr(0, 0, "CPU Usage (Last 60s)", curses.A_BOLD)
    height, width = stdscr.getmaxyx()
    graph_height = height - 2
    for i in range(min(len(cpu_history), width)):
        usage = cpu_history[-i - 1]
        bar_height = int((usage / 100) * graph_height)
        for j in range(bar_height):
            stdscr.addstr(graph_height - j, width - i - 1, '|')

def draw(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    height, width = stdscr.getmaxyx()
    offset = 0
    page = 0  # 0 = processes, 1 = summary, 2 = cpu graph
    cpu_prev = None
    cpu_history = []

    while True:
        stdscr.clear()
        if page == 0:
            draw_process_page(stdscr, offset, height, width)
        elif page == 1:
            draw_summary_page(stdscr)
        elif page == 2:
            draw_cpu_graph_page(stdscr, cpu_history)

        stdscr.addstr(height - 1, 0, f"[←/→ switch view] [↑/↓ scroll] [q to quit] Page: {page+1}")
        stdscr.refresh()
        time.sleep(1)

        # CPU history
        cpu_usage, cpu_prev = get_cpu_usage(cpu_prev)
        cpu_history.append(cpu_usage)
        if len(cpu_history) > width:
            cpu_history = cpu_history[-width:]

        try:
            key = stdscr.getch()
            if page == 0:
                if key == curses.KEY_DOWN and offset < 1000:
                    offset += 1
                elif key == curses.KEY_UP and offset > 0:
                    offset -= 1

            if key == curses.KEY_RIGHT:
                page = (page + 1) % 3
                offset = 0
            elif key == curses.KEY_LEFT:
                page = (page - 1) % 3
                offset = 0
            elif key == ord('q'):
                break
        except:
            pass

def main():
    curses.wrapper(draw)

if __name__ == "__main__":
    main()
