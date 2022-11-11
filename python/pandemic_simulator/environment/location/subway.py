from dataclasses import dataclass, field
import random
from typing import cast, Tuple, List, Dict

from ..interfaces.ids import LocationID, PersonID

from ..interfaces import BusinessLocationState, ContactRate, SimTimeTuple, NonEssentialBusinessLocationState, \
    EssentialBusinessBaseLocation, NonEssentialBusinessBaseLocation

__all__ = ['SubwayManager', 'Subway', 'SubwayState']


@dataclass
class SubwayState(BusinessLocationState):
    # 0: N, 1: S, 2: E, 3: W
    northbound: bool = False

    start_location: Tuple[int, int] = (-1, -1)
    
    speed: int = 1
    """Measured in minutes per block"""

    contact_rate: ContactRate = ContactRate(0, 0, 0, 0.0, 0.0, 0.05)

    open_time: SimTimeTuple = field(default_factory=SimTimeTuple, init=False)
    """Always open"""

    route_length: int = -1


class Subway(EssentialBusinessBaseLocation[SubwayState]):
    """Implements a subway location."""

    state_type = SubwayState
    riders: List[List[PersonID]] = []

    def configure_train(self, northbound: bool, start_location: Tuple[int, int], speed: int):
        state = cast(SubwayState, self._state)
        state.start_location = start_location
        state.northbound = northbound
        state.speed = speed
        self._uses_higher_time_scale = True
    
    def get_latest_time_at_stop(self, last_minute: int, desired_stop: Tuple[int, int]) -> int:
        state = cast(SubwayState, self._state)

        time: int = -1

        # North/South train, station reachable
        if (state.start_location[0] == desired_stop[0] and state.northbound):
            y_diff = (desired_stop[1] - state.start_location[1])
            if y_diff == 0:
                y_diff = state.route_length
            time = (last_minute / (y_diff * state.speed)) * ((y_diff * state.speed))

        # East/West train, station reachable
        if (state.start_location[1] == desired_stop[1] and not state.northbound):
            x_diff = (desired_stop[0] - state.start_location[0])
            if x_diff == 0:
                x_diff = state.route_length
            time = (last_minute / (x_diff * state.speed)) * ((x_diff * state.speed))

        return time

    def configure_riders(self):
        for i in range(60):
            temp: List[PersonID] = []
            self.riders.append(temp)
    
    def log_rider(self, person: PersonID, start_time: int, end_time: int):
        self._registry.register_person_entry_in_location(person, self.id)
        if (len(self.riders) != 60):
            self.configure_riders()
        for i in range((int)(start_time), (int)(end_time), 1):
            self.riders[i].append(person)

    def get_riders(self) -> List[List[PersonID]]:
        return self.riders


class SubwayManager():
    codes_to_subways: Dict[float, Subway] = {}
    route_entropy_factor: 0.5
    stop_frequency: int = 4
    max_train_time = 25
    train_route_length: int = 0
    walking_threshold: int = 25
    train_count: int = 0
    train_capacity: int = 0

    def __init__(self, route_entropy_factor: float, stop_frequency: int, max_train_time: int, train_route_length: int, train_capacity: int):
        self.route_entropy_factor = route_entropy_factor
        self.stop_frequency = stop_frequency
        self.max_train_time = max_train_time
        self.train_route_length = train_route_length
        self.train_capacity = train_capacity

    # Adds the subway to the collection for routing.
    def add_subway(self, subway_code: float, subway: Subway) -> None:
        subway.state.route_length = self.train_route_length
        self.codes_to_subways[subway_code] = subway
    
    # Returns time the person leaves their start location
    def commute(self, person: PersonID, start_location: Tuple[int, int], end_location: Tuple[int, int]) -> int:
        # From location coordinates, compute nearest stop coordinates:
        origin_stop_coordinates = (self.stop_frequency * (int)(start_location[0] / self.stop_frequency), self.stop_frequency * (int)(start_location[1] / self.stop_frequency))
        destination_stop_coordinates = (self.stop_frequency * (int)(end_location[0] / self.stop_frequency), self.stop_frequency * (int)(end_location[1] / self.stop_frequency))

        if (origin_stop_coordinates == destination_stop_coordinates):
            return 60

        manhattan_distance = abs(end_location[1] - start_location[1]) + abs(end_location[0] - start_location[0])

        if (manhattan_distance < self.walking_threshold):
            # They will walk
            return 60 - manhattan_distance

        departure_time = -1
        if (origin_stop_coordinates[0] == destination_stop_coordinates[0]):
            self.train_count = self.train_count + 1
            # Only need 1 North/South train
            # Get the train from the code
            code = float(origin_stop_coordinates[0])
            train = (self.codes_to_subways[code])
            delta = destination_stop_coordinates[1] - origin_stop_coordinates[1]
            distance = delta if delta > 0 else self.train_route_length + delta
            ride_duration = min(self.max_train_time, train.state.speed * distance)
            departure_time = train.get_latest_time_at_stop((60 - ride_duration), destination_stop_coordinates)
            train.log_rider(person, departure_time, 60)
        elif (origin_stop_coordinates[1] == destination_stop_coordinates[1]):    
            self.train_count = self.train_count + 1    
            # Only need 1 East/West train
            # Get the train from the code
            code = float(origin_stop_coordinates[1]) + 0.1
            train = (self.codes_to_subways[code])
            delta = destination_stop_coordinates[0] - origin_stop_coordinates[0]
            distance = delta if delta > 0 else self.train_route_length + delta
            ride_duration = min(self.max_train_time, train.state.speed * distance)
            departure_time = train.get_latest_time_at_stop((60 - ride_duration), destination_stop_coordinates)
            train.log_rider(person, departure_time, 60)
        else:
            # Need both a North/South and East/West train. Default is N/S first, then E/W
            route_list: List[Subway] = []
            code = float(origin_stop_coordinates[0])
            train = (self.codes_to_subways[code])
            route_list.append(train)
            code = float(destination_stop_coordinates[1]) + 0.1
            train = (self.codes_to_subways[code])
            route_list.append(train)
            # Randomly order according to route_entropy_factor
            rand = random.random()
            if (rand < self.route_entropy_factor):
                # E/W taken first, then N/S
                route_list.reverse()
                intermediate_stop = (destination_stop_coordinates[0], origin_stop_coordinates[1])
                # Compute time for last leg
                train = (route_list[1])
                delta = intermediate_stop[1] - origin_stop_coordinates[1]
                distance = delta if delta > 0 else self.train_route_length + delta
                ride_duration = min(self.max_train_time, train.state.speed * distance)
                connection_time = train.get_latest_time_at_stop((60 - ride_duration), intermediate_stop)
                train.log_rider(person, connection_time, 60)

                # Now repeat for first leg
                train = (route_list[0])
                delta = destination_stop_coordinates[0] - intermediate_stop[0]
                distance = delta if delta > 0 else self.train_route_length + delta
                ride_duration = train.state.speed * distance
                departure_time = train.get_latest_time_at_stop((connection_time - ride_duration), origin_stop_coordinates)
                train.log_rider(person, departure_time, connection_time)
            else:
                intermediate_stop = (origin_stop_coordinates[0], destination_stop_coordinates[1])
                # Compute time for last leg
                train = (route_list[1])
                delta = intermediate_stop[0] - origin_stop_coordinates[0]
                distance = delta if delta > 0 else self.train_route_length + delta
                ride_duration = min(self.max_train_time, train.state.speed * distance)
                connection_time = train.get_latest_time_at_stop((60 - ride_duration), intermediate_stop)
                train.log_rider(person, connection_time, 60)

                # Now repeat for first leg
                train = (route_list[0])
                delta = destination_stop_coordinates[1] - intermediate_stop[1]
                distance = delta if delta > 0 else self.train_route_length + delta
                ride_duration = train.state.speed * distance
                departure_time = train.get_latest_time_at_stop((connection_time - ride_duration), origin_stop_coordinates)
                train.log_rider(person, departure_time, connection_time)
        
        return departure_time
            

