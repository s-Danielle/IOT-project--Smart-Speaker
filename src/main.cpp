#include <Arduino.h>
#include "wifiModule.h"
#include "wifiCredentials.h"

// these should be defined in the wifiCredentials.h file
extern const char *ssid;
extern const char *password;


// put function declarations here:
int myFunction(int, int);

void setup() {
  // put your setup code here, to run once:
  Serial.begin(115200);
  delay(2000);
  while(!Serial){;}
  pinMode(LED_BUILTIN, OUTPUT);
  WifiModule::connect(ssid, password, 10000);
  Serial.println("called connect");
}
bool firstTime = true;
void loop() {
  if(firstTime){
    Serial.println("started loop");
    firstTime = false;
  }
  // put your main code here, to run repeatedly:
  digitalWrite(LED_BUILTIN, HIGH);
  delay(1000);
  digitalWrite(LED_BUILTIN, LOW);
  delay(1000);
}

// put function definitions here:
int myFunction(int x, int y) {
  return x + y;
}