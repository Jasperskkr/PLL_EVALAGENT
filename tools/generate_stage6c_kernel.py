"""Deterministic optional extension of frozen Euler/edge kernel; no second PLL source.

All substitutions assert unique original text. Output identity includes generator,
original source and generated source. Native tests independently check charge/events.
"""
from pathlib import Path
HERE=Path(__file__).resolve().parents[1]/'pll_allocation/verification'

RNG=r'''
// SplitMix64 specified by unsigned 64-bit operations, Box-Muller with open U(0,1).
// Each source has its own state; no std::normal_distribution implementation dependency.
struct NoiseRng {
    uint64_t state; bool spare=false; double cached=0.;
    explicit NoiseRng(uint64_t seed):state(seed){}
    uint64_t next() { uint64_t z=(state+=UINT64_C(0x9e3779b97f4a7c15));
        z=(z^(z>>30))*UINT64_C(0xbf58476d1ce4e5b9);z=(z^(z>>27))*UINT64_C(0x94d049bb133111eb);return z^(z>>31); }
    double uniform() {return ((next()>>11)+.5)*(1./9007199254740992.);}
    double normal() { if(spare){spare=false;return cached;} const double a=std::sqrt(-2*std::log(uniform()));
        const double w=6.283185307179586476925286766559*uniform();cached=a*std::sin(w);spare=true;return a*std::cos(w);}
};
// Standalone source generator: no PLL, used for free-running diffusion/source tests.
extern "C" __declspec(dllexport) int sample_process(uint64_t seed, long long n,
    double dt, double snu, double si, double on_fraction, double* out) {
    if(n<1 || dt<=0 || snu<0 || si<0 || on_fraction<0 || on_fraction>1)return -1;
    NoiseRng rv(seed^UINT64_C(0x94d049bb133111eb)),rc(seed^UINT64_C(0x8538ecb5bd456ea3)),
        ru(seed^UINT64_C(0x9e3779b97f4a7c15)),rd(seed^UINT64_C(0xbf58476d1ce4e5b9));
    for(long long i=0;i<n;i++) {
        out[4*i]=6.283185307179586476925286766559*std::sqrt(snu*dt/2)*rv.normal();
        out[4*i+1]=std::sqrt(si/(2*dt))*rc.normal();
        out[4*i+2]=on_fraction>0?std::sqrt(si*dt*on_fraction/2)*ru.normal():0.;
        out[4*i+3]=on_fraction>0?std::sqrt(si*dt*on_fraction/2)*rd.normal():0.;
    }
    return 0;
}
'''


def source():
    src=(HERE/'kernel.cpp').read_text(encoding='utf-8')
    def replace(a,b):
        nonlocal src
        if src.count(a)!=1:raise ValueError('frozen source substitution not unique: '+a[:65])
        src=src.replace(a,b,1)
    replace('int simulate(const double* p,','int simulate_nonideal(const double* p, const double* q, uint64_t seed,')
    replace('double v=p[10], u=p[10], phi=0.; bool up=false, down=false;',r'''
    const double k2=q[0], mismatch=q[1], leak=q[2], resetdelay=q[3], compliance=q[4], noiseon=q[5];
    const double refsigma=q[6], snu=q[7], sicp=q[8], svr=q[9], siup=q[10], sidown=q[11];
    const double vstar=(N*fref-f0)/kv;
    NoiseRng rr(seed^UINT64_C(0xd1b54a32d192ed03)),rv(seed^UINT64_C(0x94d049bb133111eb)),
        rc(seed^UINT64_C(0x8538ecb5bd456ea3)),rt(seed^UINT64_C(0xda3e39cb94b95bdb)),
        ru(seed^UINT64_C(0x9e3779b97f4a7c15)),rd(seed^UINT64_C(0xbf58476d1ce4e5b9));
    double resetat=INFINITY, charge=0.,clampcharge=0.,branchcharge=0.,uptime=0.,downtime=0.,
        upnoise=0.,downnoise=0.,cpnoise=0.,rnoise=0.,vconphase=0.; long long resets=0;
    double v=p[10], u=p[10], phi=0.; bool up=false, down=false;
    double refl=0.,refr=0.; long long refcell=-1;
    auto refnoise=[&](double t) {
        if(refsigma==0 || t<noiseon)return 0.;
        double x=(t-noiseon)*fref;long long index=(long long)std::floor(x);
        while(refcell<index){refl=refr;refr=refsigma*rr.normal();refcell++;}
        return refl+(refr-refl)*(x-index);
    };''')
    replace('auto rphase=[&](double t) { return twopi*fref*t+(t>=onset ? amplitude*std::sin(twopi*fm*(t-onset)):0.); };',
            'auto rphase=[&](double t) { return twopi*fref*t+(t>=onset && t<q[12] ? amplitude*std::sin(twopi*fm*(t-onset)):0.)+refnoise(t); };')
    for i in range(6):
        a='trace[6*count'+(']' if i==0 else '+'+str(i)+']')
        replace(a,a.replace('6*count','28*count'))
    replace('        count++; return true;',r'''
        trace[28*count+6]=phi; trace[28*count+7]=f0+kv*v+k2*v*(v-vstar);
        trace[28*count+8]=double(up);trace[28*count+9]=double(down);
        trace[28*count+10]=charge;trace[28*count+11]=clampcharge;trace[28*count+12]=branchcharge;
        trace[28*count+13]=uptime;trace[28*count+14]=downtime;
        trace[28*count+15]=upnoise;trace[28*count+16]=downnoise;trace[28*count+17]=double(resets);
        trace[28*count+18]=refnoise(t);trace[28*count+19]=cpnoise;trace[28*count+20]=rnoise;
        trace[28*count+21]=vconphase;trace[28*count+22]=double(rcount);trace[28*count+23]=double(dcount);
        trace[28*count+24]=std::isfinite(resetat)?resetat:-1.;trace[28*count+25]=c1*(v-p[10])+c2*(u-p[10]);
        trace[28*count+26]=p[10];trace[28*count+27]=kv+k2*(2*v-vstar);
        count++; return true;''')
    replace('const double t=k*dt, ref0=rphase(t), div0=phi/N, f=f0+kv*v;',r'''
        const double t=k*dt, ref0=rphase(t), div0=phi/N, f=f0+kv*v+k2*v*(v-vstar);
        const bool enabled=t>=noiseon;
        const double dn=(enabled && snu>0 && k<n-1)?std::sqrt(snu*dt/2)*twopi*rv.normal():0.;
        const double phaseinc=twopi*f*dt+dn;
        if(phaseinc<=0 || phaseinc/N>=twopi)return -8;''')
    replace('const double ref1=rphase(t+dt), div1=(phi+twopi*f*dt)/N;',
            'const double ref1=rphase(t+dt), div1=(phi+phaseinc)/N;')
    begin=src.index('        double area=0.,prev=0.;')
    end=src.index('        const double branch=(v-u)/R, next=v+dt*(area-branch)/c1;',begin)
    src=src[:begin]+r'''
        // Integrate actual UP/DOWN/reset subintervals; pulse amplitudes fixed at Euler v.
        const double iup=I*(1+mismatch/2)*(1+compliance*(v-vstar));
        const double idown=I*(1-mismatch/2)*(1+compliance*(v-vstar));
        double area=0.,prev=0.,tauup=0.,taudown=0.;bool rdone=!re,ddone=!de;
        for(int event=0;event<8;event++) {
            double nexta=1.;int kind=0;
            if(!rdone && ra<=nexta){nexta=ra;kind=1;}
            if(!ddone && (da<nexta || (kind==0 && da==nexta))){nexta=da;kind=2;}
            const double reseta=(resetat-t)/dt;
            // A reset at a prior step endpoint can round just before this step's t.
            // It remains due; discarding it would latch both PFD outputs forever.
            // Permit only roundoff (<1e-5 step); larger overdue resets are errors.
            if(reseta < -1e-5)return -10;
            if(reseta<=nexta){nexta=std::max(prev,reseta);kind=3;}
            const double interval=nexta-prev;
            area+=interval*(iup*int(up)-idown*int(down));
            tauup+=interval*dt*int(up);taudown+=interval*dt*int(down);prev=nexta;
            if(kind==0)break;
            if(kind==1){up=true;rdone=true;}
            else if(kind==2){down=true;ddone=true;}
            else {up=down=false;resetat=INFINITY;resets++;}
            if(up && down && !std::isfinite(resetat))resetat=t+nexta*dt+resetdelay;
            if(event==7)return -9;
        }
        uptime+=tauup;downtime+=taudown;
        const double qu=(enabled && siup>0 && tauup>0)?std::sqrt(siup*tauup/2)*ru.normal():0.;
        const double qd=(enabled && sidown>0 && taudown>0)?std::sqrt(sidown*taudown/2)*rd.normal():0.;
        const double qc=(enabled && sicp>0)?std::sqrt(sicp*dt/2)*rc.normal():0.;
        const double er=(enabled && svr>0)?std::sqrt(svr/(2*dt))*rt.normal():0.;
        upnoise+=qu;downnoise+=qd;cpnoise+=qc; rnoise+=dt*er/R;
        area+=leak+(qu-qd+qc)/dt;charge+=dt*area;
        const double branch=(v-u-er)/R, next=v+dt*(area-branch)/c1;
        branchcharge+=dt*branch;
        clampcharge+=c1*(std::clamp(next,lo,hi)-next);
''' + src[end+len('        const double branch=(v-u)/R, next=v+dt*(area-branch)/c1;'):]
    replace('phi+=twopi*f*dt;','phi+=phaseinc;vconphase+=dn;')
    replace('summary[12]=phi;',r'''summary[12]=phi;
    summary[13]=charge;summary[14]=clampcharge;summary[15]=branchcharge;
    summary[16]=uptime;summary[17]=downtime;summary[18]=upnoise;summary[19]=downnoise;
    summary[20]=cpnoise;summary[21]=rnoise;summary[22]=vconphase;summary[23]=double(resets);
    summary[24]=c1*(v-p[10])+c2*(u-p[10]);''')
    return '// GENERATED optional Stage6C extension; never hand edit.\n#include "kernel.cpp"\n'+RNG+src


if __name__=='__main__':
    with (HERE/'stage6c_kernel.cpp').open('x',encoding='utf-8',newline='\n') as f:f.write(source())
