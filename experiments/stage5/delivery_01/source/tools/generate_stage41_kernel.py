"""Generate isolated observation/stimulus extension, asserting frozen update text reuse."""
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]/'pll_allocation/verification'


def source():
    old = (HERE/'kernel.cpp').read_text(encoding='utf-8')
    new = old.replace('int simulate(', 'int simulate_closed_loop(', 1)
    new = new.replace('double* summary) {', 'double* summary, double* events, long long eventcap) {', 1)
    new = new.replace('double v=p[10]', 'double charge=0.; long long slips=0, eventcount=0, lastbranch=0;\n    double v=p[10]', 1)
    a = 'auto rphase=[&](double t) { return twopi*fref*t+(t>=onset ? amplitude*std::sin(twopi*fm*(t-onset)):0.); };'
    b = '''auto stimulus=[&](double t) {
        const double x=(t-onset)/p[17];
        return x<=0 ? 0. : x>=1 ? amplitude : amplitude*.5*(1-std::cos(pi*x));
    };
    auto rphase=[&](double t) { return twopi*fref*t+stimulus(t); };
    auto event=[&](double t, double kind, double value) {
        if(eventcount>=eventcap) return false;
        events[3*eventcount]=t; events[3*eventcount+1]=kind; events[3*eventcount+2]=value;
        eventcount++; return true;
    };'''
    assert a in new; new = new.replace(a, b, 1)
    for i in range(6):
        new = new.replace('trace[6*count'+(']' if i == 0 else '+'+str(i)+']'),
                          'trace[18*count'+(']' if i == 0 else '+'+str(i)+']'))
    new = new.replace('        count++; return true;', '''        trace[18*count+6]=double(up); trace[18*count+7]=double(down);
        trace[18*count+8]=charge; trace[18*count+9]=rphase(t);
        trace[18*count+10]=phi/N; trace[18*count+11]=rphase(t)-phi/N;
        trace[18*count+12]=f0+kv*v; trace[18*count+13]=double(slips);
        trace[18*count+14]=double(near); trace[18*count+15]=double(lastbranch);
        trace[18*count+16]=double(rcount); trace[18*count+17]=double(dcount);
        count++; return true;''', 1)
    new = new.replace('if(v<=lo+1e-8 || v>=hi-1e-8) near++;', '''if(v<=lo+1e-8 || v>=hi-1e-8) {
            near++; if(!event(t,2.,v)) return -6;
        }
        const long long branchindex=(long long)std::floor((ref0-div0+pi)/twopi);
        if(branchindex!=lastbranch) {
            slips+=std::abs(branchindex-lastbranch);
            if(!event(t,3.,double(branchindex-lastbranch))) return -6;
            lastbranch=branchindex;
        }''', 1)
    new = new.replace('const double branch=(v-u)/R', 'charge+=dt*area;\n        const double branch=(v-u)/R', 1)
    new = new.replace('if(next<lo || next>hi) clips++;', '''if(next<lo || next>hi) {
            clips++; if(!event(t+dt,1.,next)) return -6;
        }''', 1)
    new = new.replace('summary[12]=phi;', 'summary[12]=phi; summary[13]=double(slips); summary[14]=double(eventcount);', 1)
    # No substitution may alter the frozen physical update statements or their ordering.
    update = 'const double branch=(v-u)/R, next=v+dt*(area-branch)/c1;'
    assert update in new
    for line in ('u+=dt*branch/c2; v=std::clamp(next,lo,hi);', 'phi+=twopi*f*dt;'):
        assert line in new
    return '// Generated isolated Stage4.1 stimulus/observation extension; see generator.\n#include "kernel.cpp"\n'+new


if __name__ == '__main__':
    with (HERE/'closed_loop_kernel.cpp').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(source())
