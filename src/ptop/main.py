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

def draw_box(stdscr, y, x, h, w, title=None):
    max_y, max_x = stdscr.getmaxyx()
    # Clamp box size to fit inside the window
    h = min(h, max_y - y)
    w = min(w, max_x - x)
    if h < 2 or w < 2:
        return  # Not enough space to draw a box
    try:
        stdscr.attron(curses.A_DIM)
        stdscr.hline(y, x + 1, curses.ACS_HLINE, w - 2)
        stdscr.hline(y + h - 1, x + 1, curses.ACS_HLINE, w - 2)
        stdscr.vline(y + 1, x, curses.ACS_VLINE, h - 2)
        stdscr.vline(y + 1, x + w - 1, curses.ACS_VLINE, h - 2)
        stdscr.addch(y, x, curses.ACS_ULCORNER)
        stdscr.addch(y, x + w - 1, curses.ACS_URCORNER)
        stdscr.addch(y + h - 1, x, curses.ACS_LLCORNER)
        stdscr.addch(y + h - 1, x + w - 1, curses.ACS_LRCORNER)
        if title and w > 4:
            stdscr.addstr(y, x + 2, f" {title} ", curses.A_BOLD)
        stdscr.attroff(curses.A_DIM)
    except curses.error:
        pass  # Ignore drawing errors if box doesn't fit

def draw_process_page(stdscr, offset, height, width):
    box_h = height - 2
    box_w = width - 2
    draw_box(stdscr, 0, 0, box_h + 2, box_w + 2, title="Processes")
    stdscr.addstr(1, 2, " PID   USER       CPU%   MEM%   COMMAND", curses.A_BOLD)
    processes = read_processes()
    for idx, proc in enumerate(processes[offset:offset + box_h - 2]):
        line = f"{proc['pid']:5}  {proc['user'][:10]:10}  {proc['cpu']:5.1f}  {proc['mem']:5.1f}  {proc['cmd'][:box_w - 35]}"
        stdscr.addstr(idx + 2, 2, line)

def draw_summary_and_cpu_page(stdscr, cpu_history):
    height, width = stdscr.getmaxyx()
    mid = width // 2
    box_h = height - 2
    left_w = mid - 1
    right_w = width - mid - 1
    # Left pane: summary
    draw_box(stdscr, 0, 0, box_h + 2, left_w + 2, title="System Summary")
    used, free, total = get_memory_info()
    load = get_load_average()
    uptime = get_uptime()
    cpu_count = os.cpu_count()
    stdscr.addstr(2, 2, f"Uptime: {uptime:.0f} seconds")
    stdscr.addstr(3, 2, f"Memory: {used} KB used / {total} KB total")
    stdscr.addstr(4, 2, f"Load Avg: {load}")
    stdscr.addstr(5, 2, f"CPU Cores: {cpu_count}")
    # Right pane: CPU graph
    draw_box(stdscr, 0, mid, box_h + 2, right_w + 2, title="CPU Usage (Last 60s)")
    graph_height = box_h
    graph_width = right_w
    for i in range(min(len(cpu_history), graph_width)):
        usage = cpu_history[-i - 1]
        bar_height = int((usage / 100) * graph_height)
        for j in range(bar_height):
            stdscr.addstr(graph_height - j + 1, width - i - 2, '|')

def draw(stdscr):
    curses.curs_set(0)
    stdscr.nodelay(True)
    min_height, min_width = 16, 60
    offset = 0
    page = 0  # 0 = processes, 1 = summary+cpu
    prev_page = None
    cpu_prev = None
    cpu_history = []

    while True:
        height, width = stdscr.getmaxyx()
        if height < min_height or width < min_width:
            stdscr.clear()
            msg = f"Terminal too small! Please resize to at least {min_width}x{min_height}."
            stdscr.addstr(0, 0, msg, curses.A_BOLD)
            stdscr.refresh()
            time.sleep(1)
            prev_page = None  # force clear after resize
            continue
        if page != prev_page:
            stdscr.clear()
            prev_page = page
        if page == 0:
            draw_process_page(stdscr, offset, height, width)
        elif page == 1:
            stdscr.clear() # clear screen for summary+cpu
            draw_summary_and_cpu_page(stdscr, cpu_history)

        draw_box(stdscr, height - 2, 0, 2, width, title=None)
        stdscr.addstr(height - 1, 2, f"[←/→ switch view] [↑/↓ scroll] [q to quit] Page: {page+1}")
        stdscr.refresh()
        time.sleep(0.2)

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
                page = (page + 1) % 2
                offset = 0
            elif key == curses.KEY_LEFT:
                page = (page - 1) % 2
                offset = 0
            elif key == ord('q'):
                break
        except:
            pass

def main():
    curses.wrapper(draw)

if __name__ == "__main__":
    main()
