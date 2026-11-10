// Isolated translation of baseline/python_crosscheck.py::simulate.
// Adds input phase modulation and observations; keeps edge/Euler update order.
#include <cmath>
#include <algorithm>
#include <cstdint>

extern "C" __declspec(dllexport) int simulate(const double* p, double* trace, long long capacity,
                                             double* redges, double* dedges, long long edgecap,
                                             double* summary) {
    const double pi=3.1415926535897932384626433832795, twopi=2*pi;
    const double fref=p[0], N=p[1], I=p[2], R=p[3], c1=p[4], c2=p[5], f0=p[6], kv=p[7];
    const double lo=p[8], hi=p[9], duration=p[11], amplitude=p[13], fm=p[14], onset=p[15];
    long long n=(long long)std::ceil(duration/p[12])+1;
    if(n<2 || n>200000000) return -1;
    const double dt=duration/(n-1);
    long long stride=std::max(1LL,(long long)std::floor(p[16]/dt));
    double v=p[10], u=p[10], phi=0.; bool up=false, down=false;
    long long nr=1, nd=1, count=0, clips=0, near=0, rcount=0, dcount=0;
    long long tail=(long long)(.8*n); double fsum=0, pesum=0, pe2sum=0; long long tailcount=0;
    auto rphase=[&](double t) { return twopi*fref*t+(t>=onset ? amplitude*std::sin(twopi*fm*(t-onset)):0.); };
    auto record=[&](double t) {
        if(count>=capacity) return false;
        trace[6*count]=t; trace[6*count+1]=phi/N-twopi*fref*t;
        trace[6*count+2]=rphase(t)-twopi*fref*t;
        trace[6*count+3]=v; trace[6*count+4]=u; trace[6*count+5]=(double)clips;
        count++; return true;
    };
    for(long long k=0;k<n;k++) {
        const double t=k*dt, ref0=rphase(t), div0=phi/N, f=f0+kv*v;
        if(!std::isfinite(v) || !std::isfinite(u) || !std::isfinite(phi) || f<=0) return -2;
        if(v<=lo+1e-8 || v>=hi-1e-8) near++;
        if(k>=tail) {
            double pe=std::fmod(ref0-div0+pi,twopi); if(pe<0) pe+=twopi; pe-=pi;
            fsum+=f; pesum+=pe; pe2sum+=pe*pe; tailcount++;
        }
        if(k%stride==0 || k==n-1) if(!record(t)) return -3;
        if(k==n-1) break;
        const double ref1=rphase(t+dt), div1=(phi+twopi*f*dt)/N;
        if(ref1<ref0 || ref1-ref0>=twopi || div1-div0>=twopi) return -4;
        const bool re=ref1>=twopi*nr, de=div1>=twopi*nd;
        double ra=2., da=2.;
        if(re) {ra=std::clamp((twopi*nr-ref0)/(ref1-ref0),0.,1.); nr++;
            if(rcount>=edgecap) return -5; redges[rcount++]=t+ra*dt;}
        if(de) {da=std::clamp((twopi*nd-div0)/(div1-div0),0.,1.); nd++;
            if(dcount>=edgecap) return -5; dedges[dcount++]=t+da*dt;}
        double area=0.,prev=0.;
        if(re || de) {
            bool rfirst=ra<=da;
            for(int j=0;j<(int(re)+int(de));j++) {
                bool isref=(j==0 ? rfirst : !rfirst); double alpha=isref?ra:da;
                area+=(alpha-prev)*I*(int(up)-int(down));
                if(isref) up=true; else down=true;
                if(up && down) up=down=false;
                prev=alpha;
            }
        }
        area+=(1-prev)*I*(int(up)-int(down));
        const double branch=(v-u)/R, next=v+dt*(area-branch)/c1;
        if(next<lo || next>hi) clips++;
        u+=dt*branch/c2; v=std::clamp(next,lo,hi);
        phi+=twopi*f*dt;
    }
    summary[0]=(double)n; summary[1]=dt; summary[2]=(double)count;
    summary[3]=(double)clips; summary[4]=(double)near;
    summary[5]=fsum/tailcount; summary[6]=pesum/tailcount*180/pi;
    summary[7]=std::sqrt(pe2sum/tailcount)*180/pi; summary[8]=v; summary[9]=u;
    summary[10]=(double)rcount; summary[11]=(double)dcount; summary[12]=phi;
    return 0;
}
