# EmbeddedX Android USB demo

The bridge converts VirtualEdge HTTP telemetry into EmbeddedX LAN Monitor responses. It listens on the PC loopback interface at port 8765 and supports PING, INFO, and READ. READ supplies temperature and vibration. INFO reports the sensor source.

1. Start VirtualEdge with its dashboard enabled and check http://127.0.0.1:18080/health on the PC.
2. Run the bridge on Windows with Python 3 using `py -3 tools/virtualedge-embeddedx-bridge.py` from a Windows-accessible checkout.
3. Connect your Android phone over USB, enable USB debugging, and authorize the PC. With Android platform tools on PATH, run `adb reverse tcp:8765 tcp:8765`.
4. In EmbeddedX, open Tools → LAN Monitor. Set host to 127.0.0.1 and port to 8765, leave TLS and PSK off for the USB demo, connect, and tap READ.
5. To remove the forwarding rule, run `adb reverse --remove tcp:8765`.

The QEMU demo uses simulated sensor readings. Keep the app in the foreground during the session.

[EmbeddedX Android source](https://github.com/Gokul-Madhu/embeddedx-android-workstation)
