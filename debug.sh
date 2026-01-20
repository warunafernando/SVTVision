#!/bin/bash
# Debug script for PlanA - Comprehensive system status

echo "========================================="
echo "PlanA Debug Tool"
echo "========================================="
echo ""

echo "=== PORT STATUS ==="
echo "Port 8080 (Backend):"
if lsof -ti:8080 >/dev/null 2>&1; then
    PID=$(lsof -ti:8080)
    echo "  ✓ IN USE by PID: $PID"
    ps -p $PID -o pid,cmd --no-headers 2>/dev/null | sed 's/^/    /'
    echo ""
    echo "  Testing API:"
    curl -s http://localhost:8080/api/system 2>&1 | head -3 | sed 's/^/    /' || echo "    ✗ API not responding"
else
    echo "  ✗ NOT IN USE"
fi
echo ""

echo "Port 3000 (Frontend):"
if lsof -ti:3000 >/dev/null 2>&1; then
    PID=$(lsof -ti:3000)
    echo "  ✓ IN USE by PID: $PID"
    ps -p $PID -o pid,cmd --no-headers 2>/dev/null | sed 's/^/    /'
    echo ""
    echo "  Testing HTTP:"
    curl -s -I http://localhost:3000 2>&1 | head -3 | sed 's/^/    /' || echo "    ✗ HTTP not responding"
else
    echo "  ✗ NOT IN USE"
fi
echo ""

echo "=== CAMERA STATUS ==="
if curl -s http://localhost:8080/api/cameras >/dev/null 2>&1; then
    CAMERAS=$(curl -s http://localhost:8080/api/cameras | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data.get('cameras', [])))" 2>/dev/null || echo "0")
    echo "  Discovered cameras: $CAMERAS"
    echo ""
    echo "  Camera details:"
    curl -s http://localhost:8080/api/cameras 2>&1 | python3 -c "import sys, json; data=json.load(sys.stdin); [print(f'    - {c.get(\"id\", \"unknown\")}: open={c.get(\"available\", False)}') for c in data.get('cameras', [])]" 2>/dev/null || echo "    Error fetching cameras"
else
    echo "  ✗ Cannot fetch camera list (backend not responding)"
fi
echo ""

echo "=== DEBUG TREE ==="
if curl -s http://localhost:8080/api/debug/tree >/dev/null 2>&1; then
    curl -s http://localhost:8080/api/debug/tree 2>&1 | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    def print_node(node, indent=0):
        prefix = '  ' * indent
        status = node.get('status', '?')
        name = node.get('name', '?')
        reason = node.get('reason', '')
        metrics = node.get('metrics', {})
        fps = metrics.get('fps', 0)
        drops = metrics.get('drops', 0)
        print(f'{prefix}• {name}: {status} - {reason}')
        if fps > 0 or drops > 0:
            print(f'{prefix}  FPS: {fps}, Drops: {drops}')
        for child in node.get('children', []):
            print_node(child, indent + 1)
    print_node(data)
except Exception as e:
    print(f'  Error: {e}')
" 2>/dev/null | head -30
else
    echo "  ✗ Cannot fetch debug tree (backend not responding)"
fi
echo ""

echo "=== RECENT LOGS ==="
echo "Backend (last 10 lines):"
tail -10 /tmp/backend.log 2>/dev/null | sed 's/^/  /' || echo "  No backend log found"
echo ""
echo "Frontend (last 10 lines):"
tail -10 /tmp/frontend.log 2>/dev/null | sed 's/^/  /' || echo "  No frontend log found"
echo ""

echo "=== WEBSOCKET STATUS ==="
echo "Checking if WebSocket connections exist:"
if lsof -ti:8080 >/dev/null 2>&1; then
    WS_CONNECTIONS=$(netstat -an 2>/dev/null | grep ":8080.*ESTABLISHED" | wc -l)
    echo "  Active TCP connections to port 8080: $WS_CONNECTIONS"
else
    echo "  Cannot check (backend not running)"
fi
echo ""

echo "========================================="
