// GENERATED optional Stage6C extension; never hand edit.
#include "kernel.cpp"

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
// Isolated translation of baseline/python_crosscheck.py::simulate.
// Adds input phase modulation and observations; keeps edge/Euler update order.
#include <cmath>
#include <algorithm>
#include <cstdint>

extern "C" __declspec(dllexport) int simulate_nonideal(const double* p, const double* q, uint64_t seed, double* trace, long long capacity,
                                             double* redges, double* dedges, long long edgecap,
                                             double* summary) {
    const double pi=3.1415926535897932384626433832795, twopi=2*pi;
    const double fref=p[0], N=p[1], I=p[2], R=p[3], c1=p[4], c2=p[5], f0=p[6], kv=p[7];
    const double lo=p[8], hi=p[9], duration=p[11], amplitude=p[13], fm=p[14], onset=p[15];
    long long n=(long long)std::ceil(duration/p[12])+1;
    if(n<2 || n>200000000) return -1;
    const double dt=duration/(n-1);
    long long stride=std::max(1LL,(long long)std::floor(p[16]/dt));
    
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
    };
    long long nr=1, nd=1, count=0, clips=0, near=0, rcount=0, dcount=0;
    long long tail=(long long)(.8*n); double fsum=0, pesum=0, pe2sum=0; long long tailcount=0;
    auto rphase=[&](double t) { return twopi*fref*t+(t>=onset && t<q[12] ? amplitude*std::sin(twopi*fm*(t-onset)):0.)+refnoise(t); };
    auto record=[&](double t) {
        if(count>=capacity) return false;
        trace[28*count]=t; trace[28*count+1]=phi/N-twopi*fref*t;
        trace[28*count+2]=rphase(t)-twopi*fref*t;
        trace[28*count+3]=v; trace[28*count+4]=u; trace[28*count+5]=(double)clips;

        trace[28*count+6]=phi; trace[28*count+7]=f0+kv*v+k2*v*(v-vstar);
        trace[28*count+8]=double(up);trace[28*count+9]=double(down);
        trace[28*count+10]=charge;trace[28*count+11]=clampcharge;trace[28*count+12]=branchcharge;
        trace[28*count+13]=uptime;trace[28*count+14]=downtime;
        trace[28*count+15]=upnoise;trace[28*count+16]=downnoise;trace[28*count+17]=double(resets);
        trace[28*count+18]=refnoise(t);trace[28*count+19]=cpnoise;trace[28*count+20]=rnoise;
        trace[28*count+21]=vconphase;trace[28*count+22]=double(rcount);trace[28*count+23]=double(dcount);
        trace[28*count+24]=std::isfinite(resetat)?resetat:-1.;trace[28*count+25]=c1*(v-p[10])+c2*(u-p[10]);
        trace[28*count+26]=p[10];trace[28*count+27]=kv+k2*(2*v-vstar);
        count++; return true;
    };
    for(long long k=0;k<n;k++) {
        
        const double t=k*dt, ref0=rphase(t), div0=phi/N, f=f0+kv*v+k2*v*(v-vstar);
        const bool enabled=t>=noiseon;
        const double dn=(enabled && snu>0 && k<n-1)?std::sqrt(snu*dt/2)*twopi*rv.normal():0.;
        const double phaseinc=twopi*f*dt+dn;
        if(phaseinc<=0 || phaseinc/N>=twopi)return -8;
        if(!std::isfinite(v) || !std::isfinite(u) || !std::isfinite(phi) || f<=0) return -2;
        if(v<=lo+1e-8 || v>=hi-1e-8) near++;
        if(k>=tail) {
            double pe=std::fmod(ref0-div0+pi,twopi); if(pe<0) pe+=twopi; pe-=pi;
            fsum+=f; pesum+=pe; pe2sum+=pe*pe; tailcount++;
        }
        if(k%stride==0 || k==n-1) if(!record(t)) return -3;
        if(k==n-1) break;
        const double ref1=rphase(t+dt), div1=(phi+phaseinc)/N;
        if(ref1<ref0 || ref1-ref0>=twopi || div1-div0>=twopi) return -4;
        const bool re=ref1>=twopi*nr, de=div1>=twopi*nd;
        double ra=2., da=2.;
        if(re) {ra=std::clamp((twopi*nr-ref0)/(ref1-ref0),0.,1.); nr++;
            if(rcount>=edgecap) return -5; redges[rcount++]=t+ra*dt;}
        if(de) {da=std::clamp((twopi*nd-div0)/(div1-div0),0.,1.); nd++;
            if(dcount>=edgecap) return -5; dedges[dcount++]=t+da*dt;}

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

        if(next<lo || next>hi) clips++;
        u+=dt*branch/c2; v=std::clamp(next,lo,hi);
        phi+=phaseinc;vconphase+=dn;
    }
    summary[0]=(double)n; summary[1]=dt; summary[2]=(double)count;
    summary[3]=(double)clips; summary[4]=(double)near;
    summary[5]=fsum/tailcount; summary[6]=pesum/tailcount*180/pi;
    summary[7]=std::sqrt(pe2sum/tailcount)*180/pi; summary[8]=v; summary[9]=u;
    summary[10]=(double)rcount; summary[11]=(double)dcount; summary[12]=phi;
    summary[13]=charge;summary[14]=clampcharge;summary[15]=branchcharge;
    summary[16]=uptime;summary[17]=downtime;summary[18]=upnoise;summary[19]=downnoise;
    summary[20]=cpnoise;summary[21]=rnoise;summary[22]=vconphase;summary[23]=double(resets);
    summary[24]=c1*(v-p[10])+c2*(u-p[10]);
    return 0;
}
