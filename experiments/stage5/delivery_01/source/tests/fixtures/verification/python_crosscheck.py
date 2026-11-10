#!/usr/bin/env python3
"""Independent Python numerical crosscheck. NOT MATLAB execution or PDK validation."""
import json
from pathlib import Path
from scipy.optimize import brentq
ROOT=Path(__file__).resolve().parents[1]
import numpy as np, math, time

def simulate(*, sim_time=160e-6, dt=0.5e-9, v0=0.15, R=3820., c1=100e-12,c2=1e-9, I=100e-6, kv=20e6, f0=72e6, N=8, fref=10e6, verbose=True):
    n=math.ceil(sim_time/dt)+1; dt=sim_time/(n-1)
    v=np.empty(n); vc2=np.empty(n); fv=np.empty(n); pe=np.empty(n); cps=np.empty(n)
    v[0]=vc2[0]=v0
    phi=0.; up=False; down=False
    next_ref=1; next_div=1;
    t0=time.time()
    refd=2*math.pi*fref*dt
    vcp=0
    vmin=0.;vmax=1.2
    for k in range(n-1):
        t=k*dt
        f=f0+kv*v[k]; fv[k]=f
        ref_start=refd*k
        ref_end=refd*(k+1)
        div_start=phi/N
        div_end=(phi+2*math.pi*f*dt)/N
        r_edge=ref_end>=2*math.pi*next_ref
        d_edge=div_end>=2*math.pi*next_div
        events=[]
        if r_edge:
            alpha=(2*math.pi*next_ref-ref_start)/refd
            events.append((max(0,min(1,alpha)),1))
            next_ref+=1
        if d_edge:
            alpha=(2*math.pi*next_div-div_start)/(div_end-div_start)
            events.append((max(0,min(1,alpha)),2))
            next_div+=1
        events.sort()
        area=0.; prev=0
        for alpha,e in events:
            area+= (alpha-prev)*I*(int(up)-int(down))
            if e==1:up=True
            else:down=True
            if up and down: up=down=False
            prev=alpha
        area+=(1-prev)*I*(int(up)-int(down))
        cp=area
        cps[k]=cp
        branch=(v[k]-vc2[k])/R
        v[k+1]=max(vmin,min(vmax,v[k]+dt*(cp-branch)/c1))
        vc2[k+1]=vc2[k]+dt*branch/c2
        phi+=2*math.pi*f*dt
        error=ref_start-div_start
        pe[k]=(error+math.pi)%(2*math.pi)-math.pi
    fv[-1]=f0+kv*v[-1]
    pe[-1]=((refd*(n-1)-phi/N+math.pi)%(2*math.pi))-math.pi
    tail=slice(int(0.8*n),None)
    out={"n":n,"dt":dt,'elapsed':time.time()-t0,'fout_avg':float(np.mean(fv[tail])), 'ppm':float(1e6*(np.mean(fv[tail])-N*fref)/(N*fref)),'phase_mean_deg':float(np.mean(pe[tail])*180/math.pi),'phase_rms_deg':float(np.sqrt(np.mean(pe[tail]**2))*180/math.pi),'phase_std_deg':float(np.std(pe[tail])*180/math.pi),'freq_std_hz':float(np.std(fv[tail])),'vfinal':v[-1], 'clip_count':int(np.sum((v<=vmin+1e-8)|(v>=vmax-1e-8)))}
    bad=np.flatnonzero(abs(fv-N*fref) > 0.02*N*fref)
    out['settle_us']=(bad[-1]+1)*dt*1e6 if len(bad)>0 and bad[-1]<n-1 else math.nan
    if verbose:
        print(out)
        for us in [0.5,2,5,10,20,40,80,120,140,159]:
            kk=min(int(us*1e-6/dt),n-1); print(us, "v",round(v[kk],6),"f",round(fv[kk]/1e6,4),"pe",round(pe[kk]*180/math.pi,3),"cp",cps[min(kk,n-2)])
    return out

def kernel(f,R=3820,I=100e-6,kv=20e6,c1=100e-12,c2=1e-9,N=8):
    s=2j*np.pi*np.asarray(f)
    z=(1+s*R*c2)/(s*(c1+c2)+s*s*R*c1*c2)
    L=I*kv/N*z/s
    T=L/(1+L);E=1/(1+L)
    Hcp=2*np.pi*kv*z/s*E
    Hrz=2*np.pi*kv/s*c2/(c1+c2+s*R*c1*c2)*E
    return {'L':L,'T':T,'Href':N*T,'Hdiv':-N*T,'Hvco':E,'Hcp':Hcp,'Hrz':Hrz}

def metrics(I=100e-6,kv=20e6):
    F=np.geomspace(1,1e8,10000)
    x=kernel(F,I=I,kv=kv)
    idx=np.flatnonzero((abs(x['L'][:-1])>=1)&(abs(x['L'][1:])<1))[0]
    f0=10**brentq(lambda log:abs(kernel([10**log],I=I,kv=kv)['L'][0])-1,
                    np.log10(F[idx]),np.log10(F[idx+1]))
    pm=180+np.angle(kernel([f0],I=I,kv=kv)['L'][0],deg=True)
    idx=np.flatnonzero((abs(x['T'][:-1])>2**(-.5))&
                       (abs(x['T'][1:])<=2**(-.5)))[0]
    bw=10**brentq(lambda log:abs(kernel([10**log],I=I,kv=kv)['T'][0])-2**(-.5),
                   np.log10(F[idx]),np.log10(F[idx+1]))
    return {'PM_deg':float(pm),'UGF_Hz':float(f0),'BW_Hz':float(bw)}

def noise_validation():
    f=np.geomspace(1e3,4e6,700)
    h=kernel(f)
    terms={
        'Reference':abs(h['Href'])**2*(2*10**(-150/10)),
        'Divider':abs(h['Hdiv'])**2*(2*10**(-155/10)),
        'VCO':abs(h['Hvco'])**2*(2*10**(-105/10)*(1e5/f)**2+2*10**(-160/10)),
        'ChargePump':abs(h['Hcp'])**2*1e-24,
        'LoopFilter_Rz':abs(h['Hrz'])**2*(4*1.380649e-23*300*3820)
    }
    vals={name:float(np.trapezoid(val,f)) for name,val in terms.items()}
    total=float(np.trapezoid(sum(terms.values()),f))
    ident=abs(sum(vals.values())-total)/total
    # Nodal resistor thermal transfer, derived independently from 2x2 KCL.
    err=[]
    for idx,frequency in enumerate(f[::20]):
        z=2j*np.pi*frequency
        g=1/3820
        Y=np.array([[z*100e-12+g,-g],[-g,z*1e-9+g]])
        vint=np.linalg.solve(Y,np.array([1.,-1.]))[0] /3820
        H=vint*(2*np.pi*20e6/z)/(1+kernel([frequency])['L'][0])
        expected=kernel([frequency])['Hrz'][0]
        err.append(abs((H-expected)/expected))
    return {'jitter_rms_ps':np.sqrt(total)/(2*np.pi*80e6)*1e12,
            'variance_additivity_rel_error':ident,
            'resistor_KCL_relative_error_max':float(max(err))}

def graph_validation():
    a=json.loads((ROOT/'results/variables.json').read_text())
    b=json.loads((ROOT/'results/factors.json').read_text())
    ids={x['id'] for x in a}
    assert len(ids)==len(a)
    used=set();edge_count=0
    variable_registry=(ROOT/'graph/variable_registry.m').read_text()
    factor_registry=(ROOT/'graph/factor_registry.m').read_text()
    for v in a:assert "'id','"+v['id']+"'" in variable_registry
    for f in b:
        assert "'factor_id','"+f['factor_id']+"'" in factor_registry
        assert (ROOT/f['source_function']).is_file()
        for name in f['inputs']+f['outputs']:
            assert name in ids
            used.add(name);edge_count+=1
    assert ids==used
    return {'variables':len(a),'factors':len(b),'edges':edge_count,'orphans':len(ids-used)}

def check():
    checks={}
    def test(name,condition):
        if not condition:raise AssertionError(name)
        checks[name]='PASS'
    m=metrics();test('frequency_domain_pm',45<m['PM_deg']<70)
    test('frequency_domain_bw',100e3<m['BW_Hz']<400e3)
    r1=simulate(dt=1/(25*96e6),verbose=False)
    r2=simulate(dt=1/(34*96e6),verbose=False)
    test('baseline_event_PFD_lock',abs(r1['ppm'])<100 and r1['phase_rms_deg']<5 and r1['clip_count']==0)
    test('step_convergence',abs(r1['fout_avg']-r2['fout_avg'])<1e3 and
         abs(r1['phase_rms_deg']-r2['phase_rms_deg'])<1)
    n=noise_validation()
    test('PSD_variance_sum',n['variance_additivity_rel_error']<1e-12)
    test('Rz_thermal_noise_KCL',n['resistor_KCL_relative_error_max']<1e-10)
    s=metrics(I=140e-6,kv=20e6/1.4)
    test('coupled_Icp_Kvco_unidentifiability',abs(s['BW_Hz']-m['BW_Hz'])<1e-5
         and abs(s['PM_deg']-m['PM_deg'])<1e-8)
    g=graph_validation()
    checks['graph_closed_and_source_referenced']='PASS'
    result={'overall_status':'PASS','checks':checks,'metrics':m,
            'baseline_dt1':{k:float(v) for k,v in r1.items()},
            'baseline_dt2':{k:float(v) for k,v in r2.items()},
            'noise':n,'graph':g,
            'evidence_scope':'INDEPENDENT_PYTHON_REPRODUCTION_ONLY; MATLAB_RUNTIME_NOT_EXECUTED',
            'noise_provenance':'ILLUSTRATIVE_SYNTHETIC_NOT_VALIDATED'}
    (ROOT/'results/python_crosscheck_results.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS:',len(checks),'independent tests; Graph',g)
    print('PM deg',m['PM_deg'],'BW Hz',m['BW_Hz'])
    print('Python transient lock estimate: ppm',r1['ppm'],'phase RMS deg',r1['phase_rms_deg'])
    print('Illustrative jitter ps:',n['jitter_rms_ps'])
    print('IMPORTANT: MATLAB runtime was not executed.')
    return result

if __name__=='__main__':check()
