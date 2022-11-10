from dataclasses import dataclass

from python.pandemic_simulator.environment.interfaces.ids import LocationID, PersonID
from ..interfaces import LocationState, ContactRate, SimTime, SimTimeTuple, LocationRule, globals, BaseLocation

__all__ = ['Apartment', 'ApartmentState']

# Apartments are collections of homes connected by an elevator contact point
# Implementation wise, Apartments will contain a collection of homes, representing
# Apartment units

# simulates the contact rate in the elevators and common areas
@dataclass
class ApartmentState(LocationState):
    

    """TODO change the contact rate to match elevator contact"""
    contact_rate: ContactRate = ContactRate(0, 1, 0, 0.2, 0.25, 0.3)
    
    """ Determines the speed of the elevator """
    transit_time = 1

   

 
class Apartment(BaseLocation[ApartmentState]):

    """Implements an Apartment Location"""


    """ Tracks the visitors/riders of the elevators """
    riders: list[list[PersonID]] = []

    min_riders_for_contact: int = 2

    def configure_apartment(self ):
        self.uses_higher_time_scale = True

    def sync(self, sim_time: SimTime) -> None:
        super().sync(sim_time)

    def update_rules(self, new_rule: LocationRule) -> None:
        pass


    """ Configure the riders list to track contact list for each minute of the hour"""
    def configure_riders(self):
        for i in range(60):
            temp: list[PersonID] = []
            self.riders.append(temp)

    def log_rider(self, person: PersonID, start_time: int):
        if (len(self.riders) != 60):
            self.configure_riders()
        end_time = start_time + self.state.transit_time
        for i in range((int)(start_time), (int)(end_time), 1):
            self.riders[i].append(person)

    def get_riders(self) -> list[list[PersonID]]:
        return self.riders