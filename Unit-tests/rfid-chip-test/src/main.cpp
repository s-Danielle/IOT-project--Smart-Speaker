#include <SPI.h>
#include <MFRC522.h>

// Define the pins used for the module
#define SS_PIN  5
#define RST_PIN 4

// Create an instance of the MFRC522 class
MFRC522 rfid(SS_PIN, RST_PIN);

void setup() {
  Serial.begin(115200);
  
  // Wait for serial port to connect (necessary for native USB boards)
  while (!Serial); 

  SPI.begin(); // Init SPI bus
  rfid.PCD_Init(); // Init MFRC522

  Serial.println("Scan a tag");
}

void loop() {
  // 1. Look for new cards
  if (!rfid.PICC_IsNewCardPresent()) {
    return;
  }

  // 2. Select one of the cards
  if (!rfid.PICC_ReadCardSerial()) {
    return;
  }

  // 3. Show UID on serial monitor
  Serial.print("UID tag :");
  String content= "";
  
  for (byte i = 0; i < rfid.uid.size; i++) {
    Serial.print(rfid.uid.uidByte[i] < 0x10 ? " 0" : " ");
    Serial.print(rfid.uid.uidByte[i], HEX);
    content.concat(String(rfid.uid.uidByte[i] < 0x10 ? " 0" : " "));
    content.concat(String(rfid.uid.uidByte[i], HEX));
  }
  
  Serial.println();
  Serial.print("Message : ");
  content.toUpperCase();
  

  // 4. Halt PICC (Stop reading the card until removed and replaced)
  rfid.PICC_HaltA();
  
  // 5. Stop encryption on PCD
  rfid.PCD_StopCrypto1();
}