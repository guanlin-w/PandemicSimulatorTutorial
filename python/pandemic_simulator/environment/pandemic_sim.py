# Confidential, Copyright 2020, Sony Corporation of America, All rights reserved.

from collections import defaultdict, OrderedDict
from itertools import product as cartesianproduct, combinations
from random import randint, random
from typing import DefaultDict, Dict, List, Optional, Sequence, cast, Type

import numpy as np
from orderedset import OrderedSet
import math

from .interfaces.location import LocationSummary

from .location.subway import SubwayManager, Subway

from .location.home import Home
from .location.apartment import Apartment

from .contact_tracing import MaxSlotContactTracer
from .infection_model import SEIRModel, SpreadProbabilityParams
from .interfaces import ContactRate, ContactTracer, PandemicRegulation, PandemicSimState, PandemicTesting, \
    PandemicTestResult, \
    DEFAULT, GlobalTestingState, InfectionModel, InfectionSummary, Location, LocationID, Person, PersonID, Registry, \
    SimTime, SimTimeInterval, sorted_infection_summary, globals, PersonRoutineAssignment
from .location import Hospital
from .make_population import make_population
from .pandemic_testing_strategies import RandomPandemicTesting
from .simulator_config import PandemicSimConfig
from .simulator_opts import PandemicSimOpts

__all__ = ['PandemicSim', 'make_locations']


def make_locations(sim_config: PandemicSimConfig) -> List[Location]:
    return [config.location_type(loc_id=f'{config.location_type.__name__}_{i}',
                                 init_state=config.location_type.state_type(**config.state_opts),
                                 **config.extra_opts)  # type: ignore
            for config in sim_config.location_configs for i in range(config.num)]


class PandemicSim:
    """Class that implements the pandemic simulator."""

    _id_to_person: Dict[PersonID, Person]
    _id_to_location: Dict[LocationID, Location]
    _infection_model: InfectionModel
    _pandemic_testing: PandemicTesting
    _registry: Registry
    _contact_tracer: Optional[ContactTracer]
    _new_time_slot_interval: SimTimeInterval
    _infection_update_interval: SimTimeInterval
    _infection_threshold: int
    _numpy_rng: np.random.RandomState

    _type_to_locations: DefaultDict
    _hospital_ids: List[LocationID]
    _persons: Sequence[Person]
    _state: PandemicSimState
    _subway_manager: SubwayManager

    def __init__(self,
                 locations: Sequence[Location],
                 persons: Sequence[Person],
                 infection_model: Optional[InfectionModel] = None,
                 pandemic_testing: Optional[PandemicTesting] = None,
                 contact_tracer: Optional[ContactTracer] = None,
                 new_time_slot_interval: SimTimeInterval = SimTimeInterval(day=1),
                 infection_update_interval: SimTimeInterval = SimTimeInterval(day=1),
                 person_routine_assignment: Optional[PersonRoutineAssignment] = None,
                 infection_threshold: int = 0,
                 apartment_count: float = 0,
                 subway_density: float = 0,
                 driver_percentage: float = 1.0,
                 walking_distance: float = 10):
        """
        :param locations: A sequence of Location instances.
        :param persons: A sequence of Person instances.
        :param infection_model: Infection model instance, if None SEIR default infection model is used.
        :param pandemic_testing: PandemicTesting instance, if None RandomPandemicTesting default instance is used.
        :param contact_tracer: Optional ContactTracer instance.
        :param new_time_slot_interval: interval for updating contact tracer if that is not None. Default is set daily.
        :param infection_update_interval: interval for updating infection states. Default is set once daily.
        :param person_routine_assignment: An optional PersonRoutineAssignment instance that assign PersonRoutines to
            each person
        :param infection_threshold: If the infection summary is greater than the specified threshold, a
            boolean in PandemicSimState is set to True.
        """
        assert globals.registry, 'No registry found. Create the repo wide registry first by calling init_globals()'
        self._registry = globals.registry
        self._numpy_rng = globals.numpy_rng


        apartments = []
        num_apartments = math.floor(apartment_count)

        # set aside some homes for the apartments
        apartment_locations: Sequence[Location] = []
        new_loc: Sequence[Location] = []
        for loc in locations:
            if apartment_count != 0 and type(loc) is Home and len(apartment_locations) < num_apartments:
                apartment_locations.append(loc)
            else:
                new_loc.append(loc)
        locations = new_loc

        # Assign geographic data to locations:
        # First, determine total number of "plots" in world grid
        num_locations = len(locations)
        grid_length = int(math.sqrt(num_locations)) + 1

        # Create list of all open plots
        available_plots = []
        for i in range(grid_length):
            for j in range(grid_length):
                available_plots.append(tuple((i, j)))

        # For each location, assign it a random plot and remove from available_plots
        for loc in locations:
            plot = available_plots[randint(0, len(available_plots) - 1)]
            available_plots.remove(plot)
            loc.assign_geographic_coordinates(plot)
                
            if type(loc) is Apartment:
                apartments.append(loc)
        
        if num_apartments > 0:
            rooms = np.array_split(apartment_locations, len(apartments))
            for apartment, homes in zip(apartments,rooms):
                for home in homes:
                    home.update_apartment_complex(apartment)
                    
        # recombine the list back.
        locations += apartment_locations

        # Set up subways
        stop_frequency = max((int)(subway_density * grid_length), 1)

        self._subway_manager = SubwayManager(0.5, stop_frequency, 25, grid_length, int(len(persons) / 163), walking_distance)
        stop_frequency = self._subway_manager.stop_frequency

        subway_id_counter: int = 0
        subway_list: list = []


        for x_index in range(math.ceil(grid_length / stop_frequency)):
            x_coordinate = (int)(stop_frequency) * x_index
            y_coordinate = randint(0, grid_length - 1)
            start_location = (x_coordinate, y_coordinate)
            subway_id = "subway_" + str(subway_id_counter)
            subway_id_counter = subway_id_counter + 1
            subway: Subway = Subway(subway_id)
            subway.configure_train(True, start_location, 1)
            subway_code = x_coordinate + 0.0
            self._subway_manager.add_subway(subway_code, subway)
            locations.append(subway)
            

        for y_index in range(math.ceil(grid_length / stop_frequency)):
            y_coordinate = (int)(stop_frequency) * y_index
            x_coordinate = randint(0, grid_length - 1)

            start_location = (x_coordinate, y_coordinate)

            subway_id = "subway_" + str(subway_id_counter)
            subway_id_counter = subway_id_counter + 1
            subway: Subway = Subway(subway_id)
            subway.configure_train(True, start_location, 1)
            subway_list.append(subway)
            subway_code = y_coordinate + 0.1
            self._subway_manager.add_subway(subway_code, subway)
            locations.append(subway)


        # Assign drivers vs. non-drivers
        for person in persons:
            if random() < driver_percentage:
                person.set_uses_public_transit(False)
            person_type = type(person).__name__
            self._registry.global_location_summary[('Subway', person_type)] = LocationSummary()

        self._id_to_location = OrderedDict({loc.id: loc for loc in locations})
        assert self._registry.location_ids.issuperset(self._id_to_location)

        self._id_to_person = OrderedDict({p.id: p for p in persons})
        assert self._registry.person_ids.issuperset(self._id_to_person)

        self._infection_model = infection_model or SEIRModel()
        self._pandemic_testing = pandemic_testing or RandomPandemicTesting()
        self._contact_tracer = contact_tracer
        self._new_time_slot_interval = new_time_slot_interval
        self._infection_update_interval = infection_update_interval
        self._infection_threshold = infection_threshold

        self._type_to_locations = defaultdict(list)
        for loc in locations:
            self._type_to_locations[type(loc)].append(loc)
        self._hospital_ids = [loc.id for loc in locations if isinstance(loc, Hospital)]

        self._persons = persons

        # assign routines
        if person_routine_assignment is not None:
            for _loc in person_routine_assignment.required_location_types:
                assert _loc.__name__ in globals.registry.location_types, (
                    f'Required location type {_loc.__name__} not found. Modify sim_config to include it.')
            person_routine_assignment.assign_routines(persons)

        self._state = PandemicSimState(
            id_to_person_state={person.id: person.state for person in persons},
            id_to_location_state={location.id: location.state for location in locations},
            location_type_infection_summary={type(location): 0 for location in locations},
            global_infection_summary={s: 0 for s in sorted_infection_summary},
            global_testing_state=GlobalTestingState(summary={s: len(persons) if s == InfectionSummary.NONE else 0
                                                             for s in sorted_infection_summary},
                                                    num_tests=0),
            global_location_summary=self._registry.global_location_summary,
            sim_time=SimTime(),
            regulation_stage=0,
            infection_above_threshold=False
        )

    @classmethod
    def from_config(cls: Type['PandemicSim'],
                    sim_config: PandemicSimConfig,
                    sim_opts: PandemicSimOpts = PandemicSimOpts()) -> 'PandemicSim':
        """
        Creates an instance using config

        :param sim_config: Simulator config
        :param sim_opts: Simulator opts
        :return: PandemicSim instance
        """
        assert globals.registry, 'No registry found. Create the repo wide registry first by calling init_globals()'

        # make locations
        locations = make_locations(sim_config)

        # make population
        persons = make_population(sim_config)

        # configure apartments
        apartment_count = 0
        apartment_building_ratio = sim_config.home_apartment_ratio
        if apartment_building_ratio:    
            num_apartments = 0
            num_homes = 0
            for location in locations:
                if (isinstance(location, Apartment)):
                    num_apartments = num_apartments + 1
                if (isinstance(location, Home)):
                    num_homes = num_homes + 1
            
            home_home_count = (int)(num_apartments / apartment_building_ratio - num_apartments)

            apartment_count = num_homes - home_home_count
        # make infection model
        infection_model = SEIRModel(
            spread_probability_params=SpreadProbabilityParams(sim_opts.infection_spread_rate_mean,
                                                              sim_opts.infection_spread_rate_sigma))


        

        # setup pandemic testing
        pandemic_testing = RandomPandemicTesting(spontaneous_testing_rate=sim_opts.spontaneous_testing_rate,
                                                 symp_testing_rate=sim_opts.symp_testing_rate,
                                                 critical_testing_rate=sim_opts.critical_testing_rate,
                                                 testing_false_positive_rate=sim_opts.testing_false_positive_rate,
                                                 testing_false_negative_rate=sim_opts.testing_false_negative_rate,
                                                 retest_rate=sim_opts.retest_rate)

        # create contact tracing app (optional)
        contact_tracer = MaxSlotContactTracer(
            storage_slots=sim_opts.contact_tracer_history_size) if sim_opts.use_contact_tracer else None

        # setup sim
        return PandemicSim(persons=persons,
                           locations=locations,
                           infection_model=infection_model,
                           pandemic_testing=pandemic_testing,
                           contact_tracer=contact_tracer,
                           infection_threshold=sim_opts.infection_threshold,
                           person_routine_assignment=sim_config.person_routine_assignment,
                           apartment_count=apartment_count,
                           subway_density=sim_config.subway_density,
                           driver_percentage=sim_config.driver_percentage,
                           walking_distance=sim_config.walking_distance)

    @property
    def registry(self) -> Registry:
        """Return registry"""
        return self._registry

    def _compute_contacts(self, location: Location) -> OrderedSet:
        contacts: OrderedSet = OrderedSet()

        if location.uses_higher_time_scale:
            # For now, this should be subways and apartments
            if isinstance(location, Subway) or isinstance(location, Apartment):
                riders = location.riders
                
                for i in range(len(riders)):
                    visitors = np.array(riders[i])
                    cr = location.state.contact_rate.fraction_visitors
                    if isinstance(location, Subway):
                        rider_num_divisor_param = 5
                        rider_density_scale_factor = max(min((len(riders[i]) / rider_num_divisor_param), 4), 1)
                        cr = cr * rider_density_scale_factor
                    possible_contacts = list(combinations(visitors, 2))
                    
                    num_possible_contacts = len(possible_contacts)

                    if len(possible_contacts) == 0:
                        continue

                    fraction_sample = min(1., max(0., self._numpy_rng.normal(cr, 1e-2)))
                    real_fraction = int(fraction_sample * num_possible_contacts)

                    contact_idx = self._numpy_rng.randint(0, num_possible_contacts, real_fraction)
                    contacts.update([possible_contacts[idx] for idx in contact_idx])
            


        else:
            assignees = location.state.assignees_in_location
            visitors = location.state.visitors_in_location
            cr = location.state.contact_rate

            groups = [(assignees, assignees),
                    (assignees, visitors),
                    (visitors, visitors)]
            constraints = [(cr.min_assignees, cr.fraction_assignees),
                        (cr.min_assignees_visitors, cr.fraction_assignees_visitors),
                        (cr.min_visitors, cr.fraction_visitors)]

            

            for grp, cst in zip(groups, constraints):
                grp1, grp2 = grp
                minimum, fraction = cst

                possible_contacts = list(combinations(grp1, 2) if grp1 == grp2 else cartesianproduct(grp1, grp2))
                num_possible_contacts = len(possible_contacts)

                if len(possible_contacts) == 0:
                    continue

                fraction_sample = min(1., max(0., self._numpy_rng.normal(fraction, 1e-2)))
                real_fraction = max(minimum, int(fraction_sample * num_possible_contacts))

                # we are using an orderedset, it's repeatable
                contact_idx = self._numpy_rng.randint(0, num_possible_contacts, real_fraction)
                contacts.update([possible_contacts[idx] for idx in contact_idx])

        return contacts

    def _compute_infection_probabilities(self, contacts: OrderedSet, location_id: LocationID) -> None:
        infectious_states = {InfectionSummary.INFECTED, InfectionSummary.CRITICAL}

        for c in contacts:
            id_person1 = c[0]
            id_person2 = c[1]
            person1_state = self._id_to_person[id_person1].state
            person2_state = self._id_to_person[id_person2].state
            person1_inf_state = person1_state.infection_state
            person2_inf_state = person2_state.infection_state

            if (
                    # both are not infectious
                    (person1_inf_state is None and person2_inf_state is None) or

                    # both are already infected
                    (person1_inf_state is not None and person2_inf_state is not None and

                     person1_inf_state.summary in infectious_states and person2_inf_state.summary in infectious_states)
            ):
                continue
            elif person1_inf_state is not None and person1_inf_state.summary in infectious_states:
                spread_probability = (person1_inf_state.spread_probability *
                                      person1_state.infection_spread_multiplier)
                person2_state.not_infection_probability *= 1 - spread_probability
                person2_state.not_infection_probability_history.append((location_id,
                                                                        person2_state.not_infection_probability))
            elif person2_inf_state is not None and person2_inf_state.summary in infectious_states:
                spread_probability = (person2_inf_state.spread_probability *
                                      person2_state.infection_spread_multiplier)
                person1_state.not_infection_probability *= 1 - spread_probability
                person1_state.not_infection_probability_history.append((location_id,
                                                                        person1_state.not_infection_probability))

    def _update_global_testing_state(self, new_result: PandemicTestResult, prev_result: PandemicTestResult) -> None:
        if new_result == prev_result:
            # nothing to update
            return

            # person died - just update the test summary and __not__ the num_tests
        if new_result == PandemicTestResult.DEAD and prev_result != PandemicTestResult.DEAD:
            prv = InfectionSummary.CRITICAL if prev_result == PandemicTestResult.CRITICAL else \
                InfectionSummary.INFECTED if prev_result == PandemicTestResult.POSITIVE else InfectionSummary.NONE
            self._state.global_testing_state.summary[InfectionSummary.DEAD] += 1
            self._state.global_testing_state.summary[prv] -= 1

        # person tested positive/critical
        elif (new_result in {PandemicTestResult.POSITIVE, PandemicTestResult.CRITICAL} and
              prev_result in {PandemicTestResult.POSITIVE, PandemicTestResult.NEGATIVE, PandemicTestResult.UNTESTED}):
            new = InfectionSummary.CRITICAL if new_result == PandemicTestResult.CRITICAL else InfectionSummary.INFECTED
            prv = InfectionSummary.INFECTED if prev_result == PandemicTestResult.POSITIVE else InfectionSummary.NONE
            self._state.global_testing_state.summary[new] += 1
            self._state.global_testing_state.summary[prv] -= 1
            self._state.global_testing_state.num_tests += 1  # update number of tests

        # person tested negative after having tested as infected before
        elif (new_result == PandemicTestResult.NEGATIVE and
              prev_result in {PandemicTestResult.POSITIVE, PandemicTestResult.CRITICAL}):
            prv = InfectionSummary.CRITICAL if prev_result == PandemicTestResult.CRITICAL else InfectionSummary.INFECTED
            self._state.global_testing_state.summary[InfectionSummary.RECOVERED] += 1
            self._state.global_testing_state.summary[prv] -= 1
            self._state.global_testing_state.num_tests += 1  # update number of tests

    def step(self) -> None:
        """Method that advances one step through the simulator"""
        # sync all locations
        for location in self._id_to_location.values():
            location.sync(self._state.sim_time)
        self._registry.update_location_specific_information()

        # call person steps (randomize order) and update commutes
        for i in self._numpy_rng.randint(0, len(self._persons), len(self._persons)):
            person = self._persons[i]
            person.step(self._state.sim_time, self._contact_tracer)

            last_location_id, current_location_id = person.get_commute()
            if last_location_id == '' or current_location_id == '':
                continue

            start_location = self._id_to_location[last_location_id]
            end_location = self._id_to_location[current_location_id]
            if (start_location == end_location):
                continue
            
            start_coordinates = start_location.coordinates
            end_coordinates = end_location.coordinates

            departure_time = -1
            arrival_time = randint(30, 60)
            if (person.uses_public_transit):
                departure_time = self._subway_manager.commute(person.id, start_coordinates, end_coordinates, arrival_time)
            else:
                travel_time = min(abs(end_coordinates[0] - start_coordinates[0]) + abs(end_coordinates[1] - start_coordinates[1]), 50)
                departure_time = arrival_time - travel_time
            

            start_apartment = None
            end_apartment = None
            
            if type(start_location) is Home:
                start_apartment = start_location.apartment
            if type(end_location) is Home:
                end_apartment = end_location.apartment

            if start_apartment is not None:
                start_apartment.commute(person.id,departure_time,False)
            
            if end_apartment is not None:
                end_apartment.commute(person.id,arrival_time,True)


        for location in self._id_to_location.values():
            if isinstance(location, Subway) or isinstance(location,Apartment):
                contacts = self._compute_contacts(location)

                if self._contact_tracer:
                    self._contact_tracer.add_contacts(contacts)
                
                self._compute_infection_probabilities(contacts, location.id)
                location.riders = []

        # update person contacts
        for location in self._id_to_location.values():
            if not isinstance(location, Subway) and not isinstance(location, Apartment):
                contacts = self._compute_contacts(location)

                if self._contact_tracer:
                    self._contact_tracer.add_contacts(contacts)

                self._compute_infection_probabilities(contacts, location.id)
                


        # call infection model steps
        if self._infection_update_interval.trigger_at_interval(self._state.sim_time):
            global_infection_summary = {s: 0 for s in sorted_infection_summary}
            for person in self._id_to_person.values():
                # infection model step
                person.state.infection_state = self._infection_model.step(person.state.infection_state,
                                                                          person.id.age,
                                                                          person.state.risk,
                                                                          1 - person.state.not_infection_probability)

                if person.state.infection_state.exposed_rnb != -1.:
                    for vals in person.state.not_infection_probability_history:
                        if person.state.infection_state.exposed_rnb < 1 - vals[1]:
                            infection_location = vals[0]
                            break

                    person_location_type = self._registry.location_id_to_type(infection_location)
                    self._state.location_type_infection_summary[person_location_type] += 1

                global_infection_summary[person.state.infection_state.summary] += 1
                person.state.not_infection_probability = 1.
                person.state.not_infection_probability_history = []

                # test the person for infection
                if self._pandemic_testing.admit_person(person.state):
                    new_test_result = self._pandemic_testing.test_person(person.state)
                    self._update_global_testing_state(new_test_result, person.state.test_result)
                    person.state.test_result = new_test_result

            self._state.global_infection_summary = global_infection_summary
        self._state.infection_above_threshold = (self._state.global_testing_state.summary[InfectionSummary.INFECTED]
                                                 >= self._infection_threshold)

        self._state.global_location_summary = self._registry.global_location_summary

        if self._contact_tracer and self._new_time_slot_interval.trigger_at_interval(self._state.sim_time):
            self._contact_tracer.new_time_slot()

        # call sim time step
        self._state.sim_time.step()

    def step_day(self, hours_in_a_day: int = 24) -> None:
        for _ in range(hours_in_a_day):
            self.step()
        # Modify public transit use according to our decay function
        print(self.state.sim_time.year)

    @staticmethod
    def _get_cr_from_social_distancing(location: Location,
                                       social_distancing: float) -> ContactRate:
        new_fraction = 1 - social_distancing
        cr = location.state.contact_rate
        init_cr = location.init_state.contact_rate
        new_cr = ContactRate(cr.min_assignees,
                             cr.min_assignees_visitors,
                             cr.min_visitors,
                             new_fraction * init_cr.fraction_assignees,
                             new_fraction * init_cr.fraction_assignees_visitors,
                             new_fraction * init_cr.fraction_visitors)

        return new_cr

    def impose_regulation(self, regulation: PandemicRegulation) -> None:
        """
        Receive a regulation that updates the simulator dynamics

        :param regulation: a PandemicRegulation instance
        """
        # update location rules
        sd = regulation.social_distancing
        loc_type_rk = regulation.location_type_to_rule_kwargs

        for loc_type, locations in self._type_to_locations.items():
            rule_kwargs = {}
            if loc_type_rk is not None and loc_type in loc_type_rk:
                rule_kwargs.update(loc_type_rk[loc_type])

            if sd is not None:
                # cr is the same for all locations of a given type. So just use one location to compute the new cr.
                cr = (DEFAULT if sd == DEFAULT
                      else self._get_cr_from_social_distancing(locations[0], cast(float, sd)))
                rule_kwargs.update(dict(contact_rate=cr))

            for loc in locations:
                loc.update_rules(loc.location_rule_type(**rule_kwargs))

        # update person policy
        for person in self._id_to_person.values():
            person.receive_regulation(regulation)

        self._state.regulation_stage = regulation.stage

    @property
    def state(self) -> PandemicSimState:
        """
        Property that returns the current state of the simulator.

        :return: Current state of the simulator.
        """

        return self._state

    def reset(self) -> None:
        for location in self._id_to_location.values():
            location.reset()
        for person in self._id_to_person.values():
            person.reset()

        self._infection_model.reset()

        num_persons = len(self._id_to_person)
        self._state = PandemicSimState(
            id_to_person_state={person_id: person.state for person_id, person in self._id_to_person.items()},
            id_to_location_state={loc_id: loc.state for loc_id, loc in self._id_to_location.items()},
            location_type_infection_summary={type(location): 0 for location in self._id_to_location.values()},

            global_infection_summary={s: 0 for s in sorted_infection_summary},
            global_location_summary=self._registry.global_location_summary,
            global_testing_state=GlobalTestingState(summary={s: num_persons if s == InfectionSummary.NONE else 0
                                                             for s in sorted_infection_summary},
                                                    num_tests=0),
            sim_time=SimTime(),
            regulation_stage=0,
            infection_above_threshold=False,
        )
