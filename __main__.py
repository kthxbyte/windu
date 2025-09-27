import curses
import os
import threading
import time
from collections import deque

class ScanState:
    """A thread-safe class to hold the state of the directory scan."""
    def __init__(self):
        self.lock = threading.Lock()
        self.total_items = 0
        self.scanned_items = 0
        self.dir_count = 0
        self.file_count = 0
        self.total_size = 0
        self.current_path = ""
        self.done = False
        self.tree = None

    def update(self, path, is_file, size=0):
        with self.lock:
            self.scanned_items += 1
            self.current_path = path
            if is_file:
                self.file_count += 1
                self.total_size += size
            else:
                self.dir_count += 1

    def get_state(self):
        with self.lock:
            return (
                self.total_items, self.scanned_items, self.dir_count,
                self.file_count, self.total_size, self.current_path, self.done
            )

    def set_total_items(self, total):
        with self.lock:
            self.total_items = total

    def set_done(self, tree):
        with self.lock:
            self.done = True
            self.tree = tree

def format_bytes(size):
    """Converts bytes to a human-readable format (KB, MB, GB)."""
    if size < 1024:
        return f"{size} B"
    for unit in ['KB', 'MB', 'GB', 'TB']:
        size /= 1024.0
        if size < 1024.0:
            return f"{size:6.2f} {unit}"
    return f"{size:6.2f} PB"

def scanner_worker(path, state):
    """Scans the filesystem, builds a tree, and calculates directory sizes."""
    # --- Pass 1: Count items for progress bar ---
    total_items = 0
    for root, dirs, files in os.walk(path, topdown=True, onerror=lambda e: None):
        total_items += len(dirs) + len(files)
    state.set_total_items(total_items)

    # --- Pass 2: Build the tree ---
    root_node = {'name': os.path.basename(path), 'type': 'directory', 'size': 0, 'children': [], 'parent': None}
    path_map = {path: root_node}

    for root, dirs, files in os.walk(path, topdown=True, onerror=lambda e: None):
        parent_node = path_map[root]
        for d in dirs:
            dir_path = os.path.join(root, d)
            node = {'name': d, 'type': 'directory', 'size': 0, 'children': [], 'parent': parent_node, 'expanded': False}
            parent_node['children'].append(node)
            path_map[dir_path] = node
            state.update(dir_path, is_file=False)
            time.sleep(0.001)

        for f in files:
            file_path = os.path.join(root, f)
            try:
                size = os.path.getsize(file_path)
                is_executable = f.lower().endswith('.exe')
                node = {'name': f, 'type': 'file', 'size': size, 'parent': parent_node, 'is_executable': is_executable}
                parent_node['children'].append(node)
                state.update(file_path, is_file=True, size=size)
            except OSError:
                state.update(file_path, is_file=True, size=0)
            time.sleep(0.001)

    # --- Pass 3: Calculate directory sizes (bubble up) ---
    def calculate_dir_size(node):
        if node['type'] == 'file':
            return node['size']
        node['size'] = sum(calculate_dir_size(child) for child in node.get('children', []))
        return node['size']

    calculate_dir_size(root_node)

    # --- Pass 4: Sort all children by size ---
    def sort_children_recursively(node):
        if node['type'] == 'directory' and 'children' in node:
            node['children'].sort(key=lambda x: x['size'], reverse=True)
            for child in node['children']:
                sort_children_recursively(child)

    sort_children_recursively(root_node)
    state.set_done(root_node)

def draw_dialog(stdscr, state):
    """Draws the initial scanning progress dialog."""
    # (Code from previous step, unchanged)
    curses.curs_set(0)
    stdscr.nodelay(1)
    stdscr.timeout(100)
    while True:
        (total_items, scanned_items, dir_count, file_count,
         total_size, current_path, done) = state.get_state()
        h, w = stdscr.getmaxyx()
        box_h, box_w = 10, min(w - 4, 80)
        box_y, box_x = (h - box_h) // 2, (w - box_w) // 2
        stdscr.erase()
        box_win = stdscr.subwin(box_h, box_w, box_y, box_x)
        box_win.border()
        title = "Scanning..." if not done else "Scan Complete!"
        box_win.addstr(1, (box_w - len(title)) // 2, title)
        box_win.addstr(3, 3, f"Dirs : {dir_count:,}")
        box_win.addstr(4, 3, f"Files: {file_count:,}")
        box_win.addstr(5, 3, f"Size : {format_bytes(total_size)}")
        progress = (scanned_items / total_items) if total_items > 0 else 1
        bar_width = box_w - 6
        filled_len = int(bar_width * progress)
        bar = '█' * filled_len + '-' * (bar_width - filled_len)
        box_win.addstr(7, 3, f"[{bar}] {progress:.1%}")
        display_path = current_path
        if len(display_path) > box_w - 5:
            display_path = "..." + display_path[-(box_w - 8):]
        box_win.addstr(8, 3, ' ' * (box_w - 5))
        box_win.addstr(8, 3, display_path)
        stdscr.refresh()
        box_win.refresh()
        if done:
            time.sleep(0.5)
            break
        if stdscr.getch() in [ord('q'), ord('Q'), 27]:
            break

def draw_tree_view(stdscr, tree):
    """Draws the interactive, navigable directory tree."""
    curses.curs_set(0)
    stdscr.nodelay(0)
    
    # --- Color setup ---
    curses.start_color()
    curses.use_default_colors()
    # Pair 1: Directory (Blue)
    curses.init_pair(1, curses.COLOR_BLUE, -1) 
    # Pair 2: Executable (Green)
    curses.init_pair(2, curses.COLOR_GREEN, -1)
    # Pair 3: Regular File (Default)
    curses.init_pair(3, -1, -1)

    dir_color = curses.color_pair(1)
    exec_color = curses.color_pair(2)
    file_color = curses.color_pair(3)
    
    # Navigation state
    history = deque([tree])
    current_selection = 0
    scroll_top = 0
    sort_descending = True # Default sort order
    
    while True:
        current_node = history[-1]
        children = current_node.get('children', [])
        
        h, w = stdscr.getmaxyx()
        stdscr.erase()

        # --- Header ---
        header = f"--- {current_node['name']} --- Total Size: {format_bytes(current_node['size'])} ---"
        stdscr.addstr(0, 1, header[:w-2])
        sort_mode = "Desc" if sort_descending else "Asc"
        help_text = f"Arrows: Navigate | s: Toggle Sort ({sort_mode}) | q: Quit"
        stdscr.addstr(h - 1, 1, help_text[:w-2])

        # --- Scrolling logic ---
        if current_selection < scroll_top:
            scroll_top = current_selection
        if current_selection >= scroll_top + h - 3:
            scroll_top = current_selection - h + 4

        # --- Render visible items ---
        for i, child in enumerate(children[scroll_top : scroll_top + h - 3]):
            idx = i + scroll_top
            line = 2 + i
            
            prefix = "▸" if child['type'] == 'directory' and not child.get('expanded') else "▾"
            if child['type'] == 'file': prefix = ' '

            size_str = f"{format_bytes(child['size']):>12}"
            
            # Calculate available width for the name part, ensuring space for all components
            # w-2 (borders) -2 (prefix) -12 (size) -1 (padding) = w-17
            max_name_width = w - 17
            if max_name_width < 4: max_name_width = 4 # Ensure a minimum width

            name = child['name']
            if child['type'] == 'directory': name += '/'

            # Truncate name if it's too long to fit
            if len(name) > max_name_width:
                name = name[:max_name_width-3] + "..."
            
            prefix_str = f"{prefix} "
            
            # Construct the full line string with proper spacing
            display_line = f"{prefix_str}{name:<{max_name_width}} {size_str}"
            
            # Determine color based on file type
            color = file_color
            if child['type'] == 'directory':
                color = dir_color
            elif child.get('is_executable'):
                color = exec_color
            
            # Combine color with reverse attribute if selected
            attributes = color
            if idx == current_selection:
                attributes |= curses.A_REVERSE

            stdscr.attron(attributes)
            stdscr.addstr(line, 1, display_line[:w-2])
            stdscr.attroff(attributes)

        stdscr.refresh()

        key = stdscr.getch()

        if key == curses.KEY_UP:
            current_selection = max(0, current_selection - 1)
        elif key == curses.KEY_DOWN:
            current_selection = min(len(children) - 1, current_selection + 1)
        elif key == ord('s'):
            sort_descending = not sort_descending
            children.sort(key=lambda x: x['size'], reverse=sort_descending)
        elif key == curses.KEY_RIGHT or key == 10: # Enter
            if not children: continue
            selected_child = children[current_selection]
            if selected_child['type'] == 'directory':
                history.append(selected_child)
                current_selection = 0
                scroll_top = 0
                sort_descending = True # Reset to default sort
        elif key == curses.KEY_LEFT or key == ord('h'):
            if len(history) > 1:
                history.pop()
                current_selection = 0
                scroll_top = 0
                sort_descending = True # Reset to default sort
        elif key == ord('q'):
            break

def main(stdscr):
    """Main function to orchestrate scanning and tree view."""
    start_path = os.getcwd()
    state = ScanState()

    scanner_thread = threading.Thread(target=scanner_worker, args=(start_path, state))
    scanner_thread.daemon = True
    scanner_thread.start()

    draw_dialog(stdscr, state)
    
    state.set_done(state.tree) # Ensure done is set if dialog is quit early
    scanner_thread.join(timeout=2)

    if state.tree:
        draw_tree_view(stdscr, state.tree)

if __name__ == "__main__":
    try:
        curses.wrapper(main)
        print("Exited.")
    except curses.error as e:
        print(f"Curses error. Your terminal might not be fully compatible.")
        print(f"Error: {e}")
    except KeyboardInterrupt:
        print("Exited.")