#include "ObstacleDetectionBrightnessSensor.h"
#include "Arduino.h"

ObstacleDetectionBrightnessSensor::ObstacleDetectionBrightnessSensor(int photoresistor) {
  _photoresistor = photoresistor;
}

int ObstacleDetectionBrightnessSensor::getAverageReading(int samples) {
  int cumulativeBrightness = 0;

  for (int i = 0; i < samples; i++) {
    cumulativeBrightness += analogRead(_photoresistor);
  }

  return cumulativeBrightness /= samples;
}

bool ObstacleDetectionBrightnessSensor::detectObstacle(int samples, int reference, float marginFromReference) {
  int brightness = ObstacleDetectionBrightnessSensor::getAverageReading(samples);

  if (brightness < (1 - marginFromReference) * reference) {
    return true;
  } 

  return false;
}