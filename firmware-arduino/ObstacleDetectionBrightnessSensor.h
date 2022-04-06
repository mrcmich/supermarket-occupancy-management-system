#ifndef OBSTACLEDETECTIONBRIGHTNESSSENSOR_H
#define OBSTACLEDETECTIONBRIGHTNESSSENSOR_H

class ObstacleDetectionBrightnessSensor {
  public:
    ObstacleDetectionBrightnessSensor(int photoresistor);
    int getAverageReading(int samples);
    bool detectObstacle(int samples, int reference, float marginFromReference);
  protected:
    int _photoresistor;
};

#endif