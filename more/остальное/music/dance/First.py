import numpy as np, time, shutil, subprocess, os
from functools import lru_cache
from scipy.signal import butter, sosfilt
from scipy.io import wavfile

T0 = time.time()
SR = 44100; BPM = 120; BEAT = 60.0/BPM; BAR = 4*BEAT; NB = 108
DUR = NB*BAR; N = int(DUR*SR)          # 216.0 s = 3:36
rng = np.random.default_rng(7)

def fq(m): return 440.0*2**((m-69)/12.0)
def noise(n): return rng.standard_normal(n).astype(np.float32)

WT = {}
def saw(fr, n):                        # bandlimited saw через wavetable
    key = round(fr, 3)
    if key not in WT:
        K = max(1, min(60, int((SR/2)/fr))); x = np.arange(4096)/4096.0
        w = np.zeros(4096)
        for k in range(1, K+1): w += np.sin(2*np.pi*k*x)/k
        WT[key] = (w*(2/np.pi)).astype(np.float32)
    w = WT[key]; idx = (np.arange(n)*(fr*4096.0/SR)) % 4096
    i = idx.astype(np.int64); a = (idx-i).astype(np.float32)
    return w[i]*(1-a) + w[(i+1) % 4096]*a

SOC = {}
def filt(x, kind, cut):
    key = (kind, cut)
    if key not in SOC:
        if kind == 'b':
            SOC[key] = butter(2, [cut[0]/(SR/2), cut[1]/(SR/2)], 'bandpass', output='sos')
        else:
            SOC[key] = butter(2, cut/(SR/2), kind, output='sos')
    return sosfilt(SOC[key], x, axis=0).astype(np.float32)

def make_kick():
    n = int(0.32*SR); t = np.arange(n)/SR
    ph = 2*np.pi*np.cumsum(45+120*np.exp(-t/0.028))/SR
    x = np.sin(ph)*np.exp(-t/0.10) + noise(n)*np.exp(-t/0.003)*0.5
    return (x/np.abs(x).max()*0.9).astype(np.float32)
KICK = make_kick()

def make_clap():
    n = int(0.25*SR); t = np.arange(n)/SR
    x = noise(n)*np.exp(-t/0.06)
    for d in (0.011, 0.022):
        m = int(d*SR); x[m:] += noise(n-m)*np.exp(-t[:n-m]/0.05)*0.8
    return (filt(x, 'b', (900, 3200))*1.2).astype(np.float32)
CLAP = make_clap()

n = int(0.06*SR); HATC  = (filt(noise(n), 'highpass', 7000)*np.exp(-np.arange(n)/SR/0.015)).astype(np.float32)
n = int(0.30*SR); HATO  = (filt(noise(n), 'highpass', 6500)*np.exp(-np.arange(n)/SR/0.09)).astype(np.float32)
n = int(1.60*SR); CRASH = (filt(noise(n), 'highpass', 4500)*np.exp(-np.arange(n)/SR/0.5)).astype(np.float32)
n = int(0.18*SR); t = np.arange(n)/SR
SNARE = ((filt(noise(n), 'b', (1200, 4500)) + 0.5*np.sin(2*np.pi*190*t))*np.exp(-t/0.05)).astype(np.float32)
n = int(0.70*SR); t = np.arange(n)/SR
BOOM = (np.sin(2*np.pi*np.cumsum(30+60*np.exp(-t/0.05))/SR)*np.exp(-t/0.25)).astype(np.float32)

@lru_cache(maxsize=256)
def bass_note(m, dur):
    n = int(dur*SR); t = np.arange(n)/SR
    x = saw(fq(m+12), n)*0.7 + np.sin(2*np.pi*fq(m)*t).astype(np.float32)*0.9
    x = filt(x, 'lowpass', 650)
    return (x*np.minimum(1, t/0.004)*np.exp(-t/0.16)).astype(np.float32)

@lru_cache(maxsize=256)
def pluck(m, dur, cut):
    n = int(dur*SR); t = np.arange(n)/SR
    x = filt(saw(fq(m), n), 'lowpass', cut)
    return (x*np.exp(-t/0.09)*np.minimum(1, t/0.003)).astype(np.float32)

@lru_cache(maxsize=64)
def pad(chord, dur):
    n = int(dur*SR); t = np.arange(n)/SR
    x = np.zeros(n, np.float32)
    for m in chord:
        for d in (-0.004, 0.004): x += saw(fq(m)*(1+d), n)
    x = filt(x, 'lowpass', 1300)
    e = np.minimum(1, t/0.35)*np.clip((dur-t)/0.5, 0, 1)
    return (x*e/6).astype(np.float32)

@lru_cache(maxsize=256)
def lead(m, dur):
    n = int((dur+0.12)*SR); t = np.arange(n)/SR
    x = np.zeros(n, np.float32)
    for d in (-0.007, -0.0035, 0, 0.0035, 0.007): x += saw(fq(m)*(1+d), n)
    x = filt(x, 'lowpass', 3800)/5
    e = np.minimum(1, t/0.01)*np.clip((dur+0.12-t)/0.09, 0, 1)*(0.75+0.25*np.exp(-t/0.25))
    return (x*e).astype(np.float32)

def riser(dur):
    n = int(dur*SR); t = np.arange(n)/SR; u = t/dur
    x = filt(noise(n), 'highpass', 600)*u**2
    x += np.sin(2*np.pi*np.cumsum(180+900*u**2)/SR)*u**2*0.5
    return (x*0.5).astype(np.float32)

def cheer(dur=2.5):
    n = int(dur*SR); t = np.arange(n)/SR
    return (filt(noise(n), 'b', (800, 3500))*np.sin(np.pi*t/dur)**2*0.12).astype(np.float32)

drums = np.zeros((N, 2), np.float32); bass = np.zeros(N, np.float32)
music = np.zeros((N, 2), np.float32); fx = np.zeros((N, 2), np.float32)
def add(bus, t, s, g=1.0, pan=0.5):
    i = int(round(t*SR)); n = min(len(s), N-i)
    if n <= 0: return
    if bus.ndim == 1: bus[i:i+n] += s[:n]*g
    else:
        bus[i:i+n, 0] += s[:n]*(g*np.cos(pan*np.pi/2))
        bus[i:i+n, 1] += s[:n]*(g*np.sin(pan*np.pi/2))

PROG = [(57,60,64), (53,57,60), (55,60,64), (55,59,62)]   # Am F C G
ROOT = [33, 29, 36, 31]
MEL = [
 [(0,.5,76),(.5,.5,76),(1,.5,72),(1.5,.5,76),(2,1,81),(3,1,79)],
 [(0,1,77),(1,.5,76),(1.5,.5,72),(2,1.5,72),(3.5,.5,74)],
 [(0,1,76),(1,.5,79),(1.5,.5,76),(2,1,72),(3,.5,74),(3.5,.5,76)],
 [(0,1,74),(1,.5,71),(1.5,.5,74),(2,1.5,79)],
 [(0,.5,76),(.5,.5,76),(1,.5,72),(1.5,.5,76),(2,1,81),(3,1,84)],
 [(0,1,81),(1,.5,79),(1.5,.5,77),(2,.5,76),(2.5,.5,77),(3,1,72)],
 [(0,1,79),(1,.5,76),(1.5,.5,79),(2,1,81),(3,.5,79),(3.5,.5,76)],
 [(0,2,74),(2,.5,71),(2.5,.5,74),(3,1,71)],
]
SEC = [("intro",0,16),("build",16,24),("drop",24,40),("groove",40,56),
       ("break",56,64),("build",64,72),("drop",72,88),("outro",88,108)]
def sec(bar):
    for s,a,b in SEC:
        if a <= bar < b: return s,a,b

kick_times = []
for bar in range(NB):
    s,a,b = sec(bar); t = bar*BAR; ch = PROG[bar % 4]; rt = ROOT[bar % 4]
    if s != "outro" or bar < 104:
        add(music, t, pad(ch, BAR), 0.20 if s=="break" else (0.10 if s=="outro" else 0.15))
    if (s=="intro" and bar>=8) or s in ("build","break","groove","drop") or (s=="outro" and 96<=bar<104):
        seq = [ch[0]+12, ch[1]+12, ch[2]+12, ch[0]+24]; pat = [0,1,2,3,3,2,1,2]
        g = 0.09 if s=="drop" else 0.16; cut = 1500 if s=="break" else 2600
        for e in range(8):
            add(music, t+e*BEAT/2, pluck(seq[pat[e]], 0.24, cut), g, 0.35 if e%2 else 0.65)
    haskick = s in ("intro","build","drop","groove") or (s=="outro" and bar<104)
    if haskick:
        for bt in range(4):
            if s=="build" and bar==b-1 and bt==3: continue
            kt = t+bt*BEAT; add(drums, kt, KICK, 0.95); kick_times.append(kt)
    if (s=="intro" and bar>=8) or s in ("build","drop","groove") or (s=="outro" and bar<96):
        for bt in (1,3):
            if s=="build" and bar==b-1 and bt==3: continue
            add(drums, t+bt*BEAT, CLAP, 0.5)
    if (s=="intro" and bar>=4) or s in ("build","drop","groove") or (s=="outro" and bar<104):
        for e in range(8): add(drums, t+e*BEAT/2, HATC, 0.22 if e%2 else 0.14)
        if s in ("drop","groove"):
            for bt in range(4): add(drums, t+(bt+0.5)*BEAT, HATO, 0.18)
    if s=="drop" or (s=="outro" and bar<96):
        for bt in range(4): add(bass, t+(bt+0.5)*BEAT, bass_note(rt, 0.22), 0.55)
    if s=="groove":
        for e in range(8): add(bass, t+e*BEAT/2, bass_note(rt, 0.20), 0.5 if e%2 else 0.34)
    if s=="drop":
        for (bt,du,m) in MEL[(bar-a) % 8]:
            add(music, t+bt*BEAT, lead(m, du*BEAT), 0.30)
            if a==72: add(music, t+bt*BEAT, lead(m+12, du*BEAT), 0.08, 0.6)
    if s=="groove":
        for (bt,du,m) in MEL[(bar-a) % 8]:
            add(music, t+bt*BEAT, pluck(m, 0.3, 3000), 0.17)
    if s=="break":
        for (bt,du,m) in MEL[(bar-a) % 8]:
            add(music, t+bt*BEAT, lead(m, du*BEAT), 0.15)
    if s=="build":
        prog = (bar-a)/8.0; rate = 2 if bar-a<4 else (4 if bar-a<6 else 8); steps = 4*rate
        for i in range(steps):
            tt = t+i*BAR/steps
            if bar==b-1 and tt >= t+3*BEAT: continue
            add(drums, tt, SNARE, 0.14+0.30*prog+0.02*i/steps)
    if bar in (24,72):
        add(fx, t, CRASH, 0.30); add(fx, t, BOOM, 0.5); add(fx, t, cheer(), 0.5)
    if bar==0:   add(fx, t, CRASH, 0.12)
    if bar==88:  add(fx, t, CRASH, 0.18)
    if bar==104: add(fx, t, CRASH, 0.22)
    if bar in (16,64): add(fx, t, riser(8*BAR), 0.5)
    if bar==56: add(fx, t, cheer(3.0), 0.3)

amb = filt(noise(N), 'lowpass', 900)*(0.010+0.006*np.sin(2*np.pi*np.arange(N)/SR/7)).astype(np.float32)
add(fx, 0, amb, 1.0)

duck = np.ones(N, np.float32); L = int(0.30*SR); tt = np.arange(L)/SR
env = (0.28+0.72*(1-np.exp(-tt/0.085))).astype(np.float32)
for kt in kick_times:
    i = int(kt*SR); m = min(L, N-i)
    duck[i:i+m] = np.minimum(duck[i:i+m], env[:m])
bass *= duck; music *= duck[:, None]

m0 = music.copy()
for k,g in ((1,.28),(2,.12),(3,.05)):
    d = int(0.375*k*SR)
    music[d:,0] += m0[:-d,1]*g; music[d:,1] += m0[:-d,0]*g*0.8
del m0

master = drums + music + fx
master[:,0] += bass*0.707; master[:,1] += bass*0.707
for dt,g in ((0.031,.10),(0.047,.08),(0.067,.065),(0.089,.05),(0.113,.04),
             (0.149,.03),(0.191,.022),(0.233,.016),(0.31,.012),(0.41,.008)):
    d = int(dt*SR)
    master[d:,0] += music[:-d,1]*g; master[d:,1] += music[:-d,0]*g

master = np.tanh(master*1.15)
master = filt(master, 'highpass', 28)
master *= 0.95/np.abs(master).max()
fi = int(0.03*SR); master[:fi] *= np.linspace(0,1,fi)[:,None]
fo = int(4*SR);    master[-fo:] *= np.linspace(1,0,fo)[:,None]

wav = 'OpenAirDisco_3m36s.wav'
wavfile.write(wav, SR, (master*32767).astype(np.int16))
if shutil.which('ffmpeg'):
    subprocess.run(['ffmpeg','-y','-i',wav,'-codec:a','libmp3lame','-b:a','192k',
                    'OpenAirDisco_3m36s.mp3'], capture_output=True)
print(f"Готово: {DUR:.1f} c, файл {wav}, рендер {time.time()-T0:.1f} c")
