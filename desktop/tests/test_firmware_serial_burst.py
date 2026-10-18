"""Static guard for the streaming USB-CDC packet-burst fix."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMM = ROOT / "src" / "Communications.cpp"


class FirmwareReceiveRegressionTests(unittest.TestCase):
    def test_rx_stops_ingesting_at_capacity_without_dropping_oldest_valid_bytes(self):
        src = COMM.read_text(encoding="utf-8")
        read_section = src.split("    Command Read(void)", 1)[1].split("    void WriteImmediate(", 1)[0]
        self.assertIn(
            "while (Serial.available() && s_rxLength < RX_BUFFER_SIZE)", read_section
        )
        self.assertNotIn("DiscardRx(1);\n            s_rxBuffer[s_rxLength++]", read_section)
        self.assertIn("DiscardRx(frameLength);", read_section)
        self.assertIn("if (payloadLength > MAX_PAYLOAD)", read_section)


if __name__ == "__main__":
    unittest.main()
