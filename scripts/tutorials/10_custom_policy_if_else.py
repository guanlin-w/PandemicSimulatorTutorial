# Confidential, Copyright 2020, Sony Corporation of America, All rights reserved.

from tqdm import trange

import pandemic_simulator as ps
import random


def run_pandemic_gym_env() -> None:
    """Here we execute the gym envrionment wrapped simulator using austin regulations,
    a small town config and default person routines."""

    print('\nA tutorial that runs the OpenAI Gym environment wrapped simulator', flush=True)

    # init globals
    ps.init_globals(seed=104923490)

    # select a simulator config
    sim_config = ps.sh.small_town_config

    # make env

    wrap = ps.env.PandemicGymEnv.from_config(sim_config = sim_config, pandemic_regulations=ps.sh.austin_regulations)

    # setup viz
    viz = ps.viz.GymViz.from_config(sim_config=sim_config)
    sim_viz = ps.viz.SimViz.from_config(sim_config=sim_config)

    # run stage-0 action steps in the environment
    wrap.reset()
    Reward = 0
    
    # custom var to check for changes every 5 days
    Prev = 0
    Trajectory = 0
    Direction = 0
    for i in trange(120, desc='Simulating day'):
        
        
        if i==0:
            action = 0 

        else:
            if i%10==0:
                viz.plot()
                sim_viz.plot()
                
            #######################################################################################################################################            
            #Replace the code in the below if-else statement with your own policy, based on observation variables
            ## initial policy: if we're past day 20, set to action 1.
                ## if above threshold, set to 4 else set to 0 < this is for days before 20
            ## random policy 1: boost action if infections have been increasing in the past 15 days
                ## BOOST TO 3 IF ABOVE THRESHOLD AND IF BOOST IS 1
            Cur = obs.global_testing_summary[...,2]
            if obs.infection_above_threshold and obs.time_day[...,0]<30:
                action = 4
            else:
                if Cur - Prev > 0:
                    Trajectory += 1
                else:
                    Trajectory -= 1

                if Trajectory >= 5:
                    action = action + 1 if action < 4 else 4
                    Trajectory = 0

                if Trajectory <= -5:
                    action = action - 1 if action > 0 else 0
                    Trajectory = 0
                Prev = Cur
            # if obs.time_day[...,0]>20:
            #     action = 1
            # elif not obs.infection_above_threshold:
            #     action = 0
            # else:
            #     action = 4
            ########################################################################################################################################

        obs, reward, done, aux = wrap.step(action=int(action))  # here the action is the discrete regulation stage identifier
        print(obs)
        Reward += reward
        viz.record((obs, reward))
        sim_viz.record_state(state = wrap.pandemic_sim.state)
    # generate plots
    viz.plot()
    sim_viz.plot()
    print('Reward:'+str(Reward))


if __name__ == '__main__':
    run_pandemic_gym_env()

