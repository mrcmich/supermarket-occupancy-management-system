#ifndef CROSSINGDETECTIONFSM_H
#define CROSSINGDETECTIONFSM_H

enum CrossingDetectionFSMInputs {
  NO_OBSTACLE,
  OBSTACLE
};

enum CrossingDetectionFSMStates {
  S0,
  S1,
  S2
};

enum CrossingDetectionFSMOutputs {
  NO_CROSSING,
  CROSSING
};

class CrossingDetectionFSM {
  public:
    CrossingDetectionFSMStates getStartingState();
    CrossingDetectionFSMStates getFutureState(CrossingDetectionFSMStates currentState, CrossingDetectionFSMInputs currentInput);
    CrossingDetectionFSMOutputs getOutput(CrossingDetectionFSMStates state);
};

#endif