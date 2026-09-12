"""Evaluation-only deterministic fixtures. Never import from a policy."""
from __future__ import annotations

import math

from offline_sim.case import Case, Jammer, generate_case
from offline_sim.fields import make_error_field


def rotate(x, y, angle):
    t=math.radians(angle)
    return x*math.cos(t)-y*math.sin(t), x*math.sin(t)+y*math.cos(t)


def tail_stress_cases():
    fixtures=[]
    for index in range(4):
        angle=60.0*index
        for family in ("lost_visibility","outward_boundary","halfplane_boundary","small_reff","multitarget"):
            seed=2026091300+100*index+["lost_visibility","outward_boundary","halfplane_boundary","small_reff","multitarget"].index(family)
            x,y=(600.0,0.0)
            direction=90.1
            if family=="outward_boundary":
                x,y=rotate(1800.0,0.0,30)
                direction=30.0
            if family=="halfplane_boundary":
                x,y=(600.0,300.0)
                origin_bearing=math.degrees(math.atan2(-y,-x))
                direction=origin_bearing+90.0+(-1 if index%2 else 1)*1e-7
            if family=="small_reff":
                x,y=(1400.0,0.0); direction=179.0
            if family=="multitarget":
                x,y=(1650.0,250.0); direction=100.0
            x,y=rotate(x,y,angle)
            jammers=[Jammer(19,x,y,1000.0,"dir",(direction+angle)%360)]
            count=16 if family=="multitarget" else 10
            for k in range(1,count):
                radius=450.0+70.0*k
                px,py=rotate(radius,0.0,angle+360.0*k/(count-1))
                kind="dir" if family=="small_reff" and k%2 else "omni"
                jammers.append(Jammer(k,px,py,1000.0 if family=="small_reff" else 1300.0,kind,(angle+360*k/(count-1)+180)%360 if kind=="dir" else None))
            case=Case(jammers,make_error_field(kind="adversarial",seed=seed),seed=seed,mode="practice")
            fixtures.append((family,seed,case,19))
    # Known offline analogues, not fabricated replays of the unavailable official Run 7.
    for seed,channel in ((81,12),(9,8),(64,20),(58,15)):
        fixtures.append(("stable_bearing_replay",seed,generate_case(seed=seed,problem=4,margin_m=0.0,mode="practice",field_kind="smooth"),channel))
    return fixtures
