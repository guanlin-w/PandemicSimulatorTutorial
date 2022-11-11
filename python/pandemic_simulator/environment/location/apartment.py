from dataclasses import dataclass

from typing import List
from pandemic_simulator.environment.interfaces.ids import LocationID, PersonID
from ..interfaces import LocationState, ContactRate, SimTime, SimTimeTuple, LocationRule, globals, BaseLocation

__all__ = ['Apartment', 'ApartmentState']

# Apartments are collections of homes connected by an elevator contact point
# This emulates elevators, stairs, and hallways where potential brief interaction points
# can occur

# simulates the contact rate in the elevators and common areas
@dataclass
class ApartmentState(LocationState):
    
    """ Everyone is considered a visitor """
    contact_rate: ContactRate = ContactRate(0, 0, 0, 0, 0, 0.0033)
    
    """ Determines the speed of the elevator """
    transit_time = 1
   

 
class Apartment(BaseLocation[ApartmentState]):

    """Implements an Apartment Location"""

    state_type = ApartmentState 
    """ Tracks the visitors/riders of the elevators """
    riders: List[List[PersonID]] = []

    uses_higher_time_scale = True

    def sync(self, sim_time: SimTime) -> None:
        super().sync(sim_time)

    def update_rules(self, new_rule: LocationRule) -> None:
        pass


    """ Configure the riders list to track contact list for each minute of the hour"""
    def configure_riders(self):
        for i in range(60):
            temp: List[PersonID] = []
            self.riders.append(temp)

    def log_rider(self, person: PersonID, start_time: int, end_time: int):
        if (len(self.riders) != 60):
            self.configure_riders()
        for i in range((int)(start_time), (int)(end_time), 1):
            self.riders[i].append(person)
        

    def get_riders(self) -> List[List[PersonID]]:
        return self.riders

    """ Arrival - Destination - say they arrived at 59 """
    def commute(self,person: PersonID, time: int, destination: bool):
        
        if destination:
            """ Assume that people arrive to their destinations on the hour"""
            """ Thus, an elevator event occurs on the 60 - elevator time minute"""
            self.log_rider(person, 60 - self.state.transit_time, 60)
        else:
            """ Handle departures: need to traverse elevator before this """
            departure_time = time
            elevator_time =  departure_time - self.state.transit_time
        
            """ Assume person used the elevator on the hour if they need to leave on the hour"""
            elevator_time = 0 if elevator_time < 0 else elevator_time
            self.log_rider(person, elevator_time, departure_time)