// autore: Marco Michelini

#define DEBOUNCING_DELAY 200

// Lettura luminosità
#define PHOTORESISTOR A0

// Gestione modalità operativa sensore (ingresso/uscita)
#define LED_IN 7
#define LED_OUT 8
#define MODE_BUTTON 2

// Gestione LCD
#define LCD_RS 12
#define LCD_E 11
#define LCD_D4 6
#define LCD_D5 5
#define LCD_D6 4
#define LCD_D7 3

#include <LiquidCrystal.h>
#include "SensorMode.h"
#include "CrossingDetectionFSM.h"
#include "ObstacleDetectionBrightnessSensor.h"

/* 
*  ----------------------------------------------------------------------------------------
*  CONFIGURAZIONE PARAMETRI
*  ----------------------------------------------------------------------------------------
*/

// Il numero di campioni su cui valutare la luminosità media
const unsigned int N_SAMPLES = 15;

/*
* Fattore che determina lo scostamento dalla luminosità media necessario perché un calo di 
* luminosità venga considerato come un ostacolo; in particolare si imputa ad un ostacolo un valore
* di brightness che soddisfi la condizione:
* brightness < (1 - MARGIN_FROM_REFERENCE) * referenceBrightness
*
* N.B. Usare valori nell'intervallo (0,1)
*/
const float MARGIN_FROM_REFERENCE = 0.2;

// -----------------------------------------------------------------------------------------

// Gestione modalità operativa sensore (ingresso/uscita)
char sensorUpdate;
volatile SensorMode mode;
volatile long lastButtonPress;

// Gestore pressione tasto di selezione della modalità operativa
void modeButtonPressHandler() {
  if (millis() - lastButtonPress >= DEBOUNCING_DELAY) {
    mode = (mode == ENTRY) ? EXIT : ENTRY;
  }

  lastButtonPress = millis();
}

// Si rimanda alla documentazione relativa al formato dei pacchetti validi
boolean validatePacketHeader(unsigned char* packet, int headerLength) {
  unsigned char separator = 0xff;

  if (packet == NULL || headerLength < 1) {
    return false;
  }
  
  for (int i = 0; i < headerLength; i++) {
    if (packet[i] != separator) {
      return false;
    }
  }

  return true;
}

int integerFromBytes(unsigned char* bytes, int n) {
  int integer = 0;

  if (bytes == NULL || n < 1 || n > (int) sizeof(int)) {
    return -1;
  }
  
  for (int i = 0; i < n; i++) {
    integer = (integer << 8) | bytes[i];
  }
  
  return integer;
}

// -----------------------------------------------------------------------------------------

// Rilevazione ingresso/uscita
int reference;
long timeElapsed;
const unsigned int CROSSING_DETECTION_FSM_CLOCK = 50;
CrossingDetectionFSMStates currentState;
CrossingDetectionFSM crossingDetectionFSM;
ObstacleDetectionBrightnessSensor sensor(PHOTORESISTOR);

// Gestione LCD
const int PACKET_LENGTH = 7;
const int FEED_DATA_LENGTH = 2;
LiquidCrystal lcd(LCD_RS, LCD_E, LCD_D4, LCD_D5, LCD_D6, LCD_D7);

void setup() { 
  Serial.begin(9600);
  
  // Inizializzazione LCD
  lcd.begin(16, 2);
  lcd.setCursor(0, 0);
  lcd.print("In attesa di");
  lcd.setCursor(0, 1);
  lcd.print("Bridge...");

  // Gestione modalità operativa sensore (ingresso/uscita)
  mode = ENTRY;
  lastButtonPress = 0;
  pinMode(LED_IN, OUTPUT);
  pinMode(MODE_BUTTON, INPUT);
  pinMode(LED_OUT, OUTPUT);

  // Inizializzazione FSM per rilevazione ingresso/uscita  
  currentState = crossingDetectionFSM.getStartingState();
  reference = sensor.getAverageReading(N_SAMPLES);

  attachInterrupt(digitalPinToInterrupt(MODE_BUTTON), modeButtonPressHandler, RISING);
  
  // Inizializzazione clock FSM per rilevazione ingresso/uscita  
  timeElapsed = millis();
}

void loop() {
  int signedOccupancy = -1;
  int signedCapacity = -1;
  unsigned char predictionFeedback = 0;
  CrossingDetectionFSMInputs input;
  CrossingDetectionFSMStates futureState;
  CrossingDetectionFSMOutputs output;

  // Aggiornamento modalità operativa sensore  
  if (mode == ENTRY) {
      sensorUpdate = 1;
      digitalWrite(LED_IN, HIGH);
      digitalWrite(LED_OUT, LOW);
    } else if (mode == EXIT) {
      sensorUpdate = -1;
      digitalWrite(LED_IN, LOW);
      digitalWrite(LED_OUT, HIGH);
  } 
  
  // Aggiornamento FSM per rilevazione ingresso/uscita  
  if (millis() - timeElapsed >= CROSSING_DETECTION_FSM_CLOCK) {
    if (sensor.detectObstacle(N_SAMPLES, reference, MARGIN_FROM_REFERENCE)) {
      input = OBSTACLE;
    } else {
      input = NO_OBSTACLE;
    }

    futureState = crossingDetectionFSM.getFutureState(currentState, input);
    currentState = futureState;
    output = crossingDetectionFSM.getOutput(currentState);

    // Invio aggiornamento a bridge in caso di ingresso/uscita
    if (output == CROSSING) {
      noInterrupts();      
      Serial.write(sensorUpdate);
      interrupts();
    } 

    timeElapsed = millis();
  }

  // Lettura pacchetto di aggiornamento da bridge
  noInterrupts();
  if (Serial.available() >= PACKET_LENGTH) {
    unsigned char* packet = (unsigned char*) malloc(PACKET_LENGTH);

    if (
      packet != NULL && 
      Serial.readBytes(packet, PACKET_LENGTH) == PACKET_LENGTH &&
      validatePacketHeader(packet, FEED_DATA_LENGTH) 
    ) {
      unsigned char* occupancy_bytes = (unsigned char*) malloc(FEED_DATA_LENGTH);
      unsigned char* capacity_bytes = (unsigned char*) malloc(FEED_DATA_LENGTH);
   
      if (occupancy_bytes != NULL && capacity_bytes != NULL) {
        memcpy(occupancy_bytes, packet + FEED_DATA_LENGTH, FEED_DATA_LENGTH);
        memcpy(capacity_bytes, packet + FEED_DATA_LENGTH * 2, FEED_DATA_LENGTH);

        signedOccupancy = integerFromBytes(occupancy_bytes, FEED_DATA_LENGTH);
        signedCapacity = integerFromBytes(capacity_bytes, FEED_DATA_LENGTH);
        predictionFeedback = packet[FEED_DATA_LENGTH*3];
      }

      free(occupancy_bytes);
      free(capacity_bytes);
    }

    free(packet);
  }
  interrupts();

  // Aggiornamento LCD
  if (signedOccupancy >= 0 && signedCapacity >= 0) {
    unsigned int occupancy = (unsigned int) signedOccupancy;
    unsigned int capacity = (unsigned int) signedCapacity;
    
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print(occupancy);
    lcd.print("/");
    lcd.print(capacity);
    lcd.print(" ");
    lcd.print("persone");
    lcd.setCursor(0, 1);
    
    switch (predictionFeedback) {
      case 1:
        lcd.print("Sotto range");
        break;
      case 2:
        lcd.print("In range");
        break;
      case 3:
        lcd.print("Sopra range");
        break;
      default:
        break;
    }
  }
}
