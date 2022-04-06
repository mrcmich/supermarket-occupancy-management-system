#include "CrossingDetectionFSM.h"

CrossingDetectionFSMStates CrossingDetectionFSM::getStartingState() {
  CrossingDetectionFSMStates startingState = S0;
  return startingState;
}

CrossingDetectionFSMStates CrossingDetectionFSM::getFutureState(CrossingDetectionFSMStates currentState, CrossingDetectionFSMInputs currentInput) {
  CrossingDetectionFSMStates futureState;

  if (currentState == S0 && currentInput == OBSTACLE) {
      futureState = S1;
  } else if (currentState == S1 && currentInput == NO_OBSTACLE) {
      futureState = S2;
  } else if (currentState == S2 && currentInput == NO_OBSTACLE) {
      futureState = S0;
  } else if (currentState == S2 && currentInput == OBSTACLE) {
      futureState = S1;
  } else {
      futureState = currentState;
  }

  return futureState;
}

CrossingDetectionFSMOutputs CrossingDetectionFSM::getOutput(CrossingDetectionFSMStates state) {
  CrossingDetectionFSMOutputs output;

  if (state == S2) {
    output = CROSSING;
  } else {
    output = NO_CROSSING;
  }

  return output;
}