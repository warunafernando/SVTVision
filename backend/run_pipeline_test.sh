#!/bin/bash
# Run pipeline test: start server, open camera, run Camera→SaveVideo, check preview tap.
set -e
cd "$(dirname "$0")"
API="http://127.0.0.1:8080/api"

echo "Waiting for backend..."
for i in 1 2 3 4 5 6 7 8 9 10; do
  if curl -s -o /dev/null -w "%{http_code}" "$API/system" 2>/dev/null | grep -q 200; then
    echo "Backend ready."
    break
  fi
  [ "$i" -eq 10 ] && { echo "Backend not ready."; exit 1; }
  sleep 1
done

echo "GET /api/cameras"
CAM_RESP=$(curl -s "$API/cameras")
echo "$CAM_RESP" | head -c 500
CAM_ID=$(echo "$CAM_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); c=d.get('cameras',[]); print(c[0]['id'] if c else '')" 2>/dev/null || true)
if [ -z "$CAM_ID" ]; then
  echo "No cameras from API. Check discovery/config."
  exit 0
fi
echo "Using camera_id=$CAM_ID"

echo "POST /api/cameras/$CAM_ID/open"
OPEN_RESP=$(curl -s -w "\n%{http_code}" -X POST "$API/cameras/$CAM_ID/open" -H "Content-Type: application/json" -d '{}')
OPEN_CODE=$(echo "$OPEN_RESP" | tail -n1)
echo "Open status: $OPEN_CODE"
if [ "$OPEN_CODE" != "200" ] && [ "$OPEN_CODE" != "201" ]; then
  echo "Could not open camera (no device or permissions). Body:"
  echo "$OPEN_RESP" | head -n -1
  exit 0
fi

echo "POST /api/pipelines (Camera → SaveVideo inline)"
START_RESP=$(curl -s -w "\n%{http_code}" -X POST "$API/pipelines" -H "Content-Type: application/json" -d "{
  \"target\": \"$CAM_ID\",
  \"nodes\": [
    {\"id\": \"n1\", \"type\": \"source\", \"source_type\": \"camera\"},
    {\"id\": \"sv1\", \"type\": \"sink\", \"sink_type\": \"save_video\"}
  ],
  \"edges\": [
    {\"id\": \"e1\", \"source_node\": \"n1\", \"source_port\": \"frame\", \"target_node\": \"sv1\", \"target_port\": \"frame\"}
  ]
}")
START_BODY=$(echo "$START_RESP" | head -n -1)
START_CODE=$(echo "$START_RESP" | tail -n1)
echo "Start status: $START_CODE"
echo "$START_BODY" | python3 -m json.tool 2>/dev/null || echo "$START_BODY"

if [ "$START_CODE" != "200" ] && [ "$START_CODE" != "201" ]; then
  echo "Pipeline start failed."
  exit 1
fi

INSTANCE_ID=$(echo "$START_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id',''))" 2>/dev/null)
if [ -z "$INSTANCE_ID" ]; then
  echo "No instance id in response."
  exit 1
fi
echo "Instance id: $INSTANCE_ID"

echo "GET /api/vp/taps/$INSTANCE_ID"
TAPS_RESP=$(curl -s "$API/vp/taps/$INSTANCE_ID")
echo "$TAPS_RESP" | python3 -m json.tool

if echo "$TAPS_RESP" | grep -q '"preview"'; then
  echo "OK: preview tap present. User can click View tap and select 'preview' to see video."
else
  echo "FAIL: preview tap missing. Taps: $(echo "$TAPS_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(list(d.get('taps',{}).keys()))" 2>/dev/null)"
  exit 1
fi

echo "POST /api/pipelines/$INSTANCE_ID/stop"
curl -s -X POST "$API/pipelines/$INSTANCE_ID/stop" -o /dev/null -w "Stop status: %{http_code}\n"
echo "Done."
