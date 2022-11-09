from dataclasses import dataclass

from ..interfaces import LocationState, ContactRate, SimTime, SimTimeTuple, LocationRule, globals, BaseLocation

__all__ = ['Apartment', 'ApartmentState']

# Apartments are collections of homes connected by an elevator contact point
# Implementation wise, Apartments will contain a collection of homes, representing
# Apartment units

# simulates the contact rate in the elevators and common areas
@dataclass
def ApartmentState(LocationState):
    test_rate = 0


def Apartment(BaseLocation[ApartmentState])
    def sync(self, sim_time: SimTime) -> None:
        super().sync(sim_time)

    def update_rules(self, new_rule: LocationRule) -> None:
        pass

