/*
 * Precursor node: example ESP32 sketch (Arduino framework).
 *
 * STATUS: EXAMPLE ONLY. NOT TESTED ON HARDWARE. It compiles conceptually against the
 * standard ESP32 Arduino core APIs but has not been flashed or run by the author.
 * The analogue-to-engineering-unit conversions below are placeholders; replace them
 * with calibration for your own sensors.
 *
 * It posts one reading per second to  POST /api/ingest  on a Precursor server started
 * with:  python -m precursor serve --ingest --host 0.0.0.0
 *
 * Setup: copy secrets.h.example to secrets.h (git-ignored) and fill it in.
 * Channel names MUST match config/default.yaml.
 */
#include <WiFi.h>
#include <HTTPClient.h>
#include "secrets.h"

const uint32_t SAMPLE_PERIOD_MS = 1000;
const int PIN_CURRENT = 34, PIN_VIBRATION = 35, PIN_TEMP = 32, PIN_VOLTAGE = 33;

// Placeholder conversions (ADC counts 0..4095 -> engineering units). Calibrate!
float readCurrentA()  { return analogRead(PIN_CURRENT)   * (10.0f / 4095.0f); }
float readVibrationG(){ return analogRead(PIN_VIBRATION) * (2.0f  / 4095.0f); }
float readTempC()     { return analogRead(PIN_TEMP)      * (100.0f / 4095.0f); }
float readVoltageV()  { return analogRead(PIN_VOLTAGE)   * (15.0f / 4095.0f); }

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) { delay(500); }
}

void setup() {
  Serial.begin(115200);
  connectWifi();
}

void loop() {
  static uint32_t last = 0;
  if (millis() - last < SAMPLE_PERIOD_MS) return;
  last = millis();

  if (WiFi.status() != WL_CONNECTED) { connectWifi(); }

  char body[256];
  snprintf(body, sizeof(body),
           "{\"values\":{\"motor_current_a\":%.3f,\"vibration_g\":%.3f,"
           "\"bearing_temp_c\":%.2f,\"supply_voltage_v\":%.3f}}",
           readCurrentA(), readVibrationG(), readTempC(), readVoltageV());

  HTTPClient http;
  http.begin(String(PRECURSOR_URL) + "/api/ingest");
  http.addHeader("Content-Type", "application/json");
  if (strlen(PRECURSOR_API_KEY) > 0) http.addHeader("X-API-Key", PRECURSOR_API_KEY);
  int code = http.POST((uint8_t *)body, strlen(body));   // server assigns the timestamp
  if (code != 200) Serial.printf("ingest failed: %d\n", code);
  http.end();
}
