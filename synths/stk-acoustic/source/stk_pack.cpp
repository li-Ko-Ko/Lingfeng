// Lingfeng synth-pack ABI 1. MIT; STK algorithms retain their upstream license.
// All voices are allocated when a channel is prepared, never in noteOn/render.
#include "Rhodey.h"
#include "Wurley.h"
#include "BeeThree.h"
#include "TubeBell.h"
#include "Plucked.h"
#include "StifKarp.h"
#include "Bowed.h"
#include "Brass.h"
#include "Clarinet.h"
#include "Flute.h"
#include "Saxofony.h"
#include "BandedWG.h"
#include "Sitar.h"
#include "BlowHole.h"
#include "BlowBotl.h"
#include "Recorder.h"
#include "PercFlut.h"
#include "FMVoices.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <memory>
#include <string>
#include <vector>

#define API extern "C" __declspec(dllexport)
namespace {
thread_local std::string error;
std::unique_ptr<stk::Instrmnt> instrument(int model) {
    switch(model) {
    case 0: return std::make_unique<stk::Rhodey>();
    case 1: return std::make_unique<stk::Wurley>();
    case 2: return std::make_unique<stk::Plucked>(8.0);
    case 3: return std::make_unique<stk::StifKarp>(8.0);
    case 4: return std::make_unique<stk::Bowed>(8.0);
    case 5: return std::make_unique<stk::BeeThree>();
    case 6: return std::make_unique<stk::TubeBell>();
    case 7: return std::make_unique<stk::Brass>(8.0);
    case 8: return std::make_unique<stk::Clarinet>(8.0);
    case 9: return std::make_unique<stk::Flute>(8.0);
    case 10:return std::make_unique<stk::Saxofony>(8.0);
    case 11:return std::make_unique<stk::BandedWG>();
    case 12:return std::make_unique<stk::Sitar>(8.0);
    case 13:return std::make_unique<stk::BlowHole>(8.0);
    case 14:return std::make_unique<stk::BlowBotl>();
    case 15:return std::make_unique<stk::Recorder>();
    case 16:return std::make_unique<stk::PercFlut>();
    case 17:return std::make_unique<stk::FMVoices>();
    default:throw std::runtime_error("Unknown STK model");
    }
}
struct Voice {
    std::unique_ptr<stk::Instrmnt> synth;
    int key=-1, release=0, age=0;
    bool down=false;
    double last=0, tail=0;
    int cross=0;
    double previous=0, dc=0, low1=0, low2=0, alpha=1, velocityGain=1;
    void resetFilter(){previous=dc=low1=low2=0;}
};
struct Engine {
    std::vector<Voice> voices;
    double volume=100.0/127, expression=1, pan=.5, bend=0;
    bool sustain=false;
    double cutoff=0;
    int model;
    static constexpr int releaseFrames=5292; // 120 ms maximum release
    explicit Engine(int model,int count):model(model) {
        voices.resize(count);
        for(auto &v:voices)v.synth=instrument(model);
    }
    double frequency(int key) {return 440*std::pow(2.0,(key-69+bend)/12);}
    void tone(Voice &v){
        double hz=std::min(16000.0,std::max(cutoff,frequency(v.key)*1.5));
        v.alpha=cutoff>0 ? 1-std::exp(-6.283185307179586*hz/44100) : 1;
    }
    void release(Voice &v) {v.down=false;v.release=releaseFrames;v.synth->noteOff(.5);}
    void event(int status,int a,int b) {
        int kind=status&0xf0;
        if(kind==0x90 && b) {
            // Retrigger a repeated key in its own voice; independent channels
            // have independent engines, including the two audition channels.
            Voice *slot=nullptr;
            for(auto &v:voices)if(v.key==a){slot=&v;break;}
            if(!slot)for(auto &v:voices)if(v.key<0){slot=&v;break;}
            if(!slot)slot=&*std::max_element(voices.begin(),voices.end(),[](auto &x,auto &y){return x.age<y.age;});
            auto &v=*slot;v.tail=v.last;v.cross=88;v.synth->clear();v.resetFilter();
            double velocity=b/127.0;
            // The lip model needs a minimum breath pressure to oscillate.
            // Keep low MIDI velocities audible through a separate output gain.
            double excitation=model==7 ? std::max(.7,velocity) : velocity;
            v.velocityGain=velocity/excitation;
            v.synth->noteOn(frequency(a),excitation);v.key=a;tone(v);v.down=true;v.age=0;v.release=0;
        } else if(kind==0x80 || (kind==0x90 && !b)) {
            for(auto &v:voices)if(v.key==a && v.down){v.down=false;if(!sustain)release(v);}
        } else if(kind==0xe0) {
            bend=((b<<7|a)-8192)/8192.0*2;
            for(auto &v:voices)if(v.key>=0){v.synth->setFrequency(frequency(v.key));tone(v);}
        } else if(kind==0xb0) {
            if(a==7)volume=b/127.0;
            else if(a==11)expression=b/127.0;
            else if(a==10)pan=b/127.0;
            else if(a==64){sustain=b>=64;if(!sustain)for(auto &v:voices)if(v.key>=0&&!v.down&&!v.release)release(v);}
            else if(a==120){for(auto &v:voices){v.key=-1;v.last=0;v.synth->clear();v.resetFilter();}}
            else if(a==123){for(auto &v:voices)if(v.key>=0)release(v);}
            else if(a==121){volume=100.0/127;expression=1;pan=.5;bend=0;sustain=false;
                for(auto &v:voices)if(v.key>=0){v.synth->setFrequency(frequency(v.key));if(!v.down&&!v.release)release(v);}}
        }
    }
    void render(float *out,int frames) {
        double left=std::cos(pan*1.5707963267948966)*volume*expression;
        double right=std::sin(pan*1.5707963267948966)*volume*expression;
        for(int i=0;i<frames;++i) {
            double sum=0;
            for(auto &v:voices)if(v.key>=0) {
                double s=v.synth->tick();
                // Reject unstable feedback before it reaches the master
                // limiter. Remove DC and damp excess upper partials per preset;
                // cutoff follows high notes so the piano range stays usable.
                if(!std::isfinite(s)||std::abs(s)>64){v.key=-1;v.last=0;v.resetFilter();continue;}
                double dc=s-v.previous+.997153* v.dc;v.previous=s;v.dc=dc;
                v.low1+=v.alpha*(dc-v.low1);v.low2+=v.alpha*(v.low1-v.low2);s=v.low2*v.velocityGain;
                // Smooth activation/voice stealing and release without a
                // constantly saturating waveshaper on the master output.
                if(v.cross){double t=v.cross/88.0;s=s*(1-t)+v.tail*t;--v.cross;}
                if(v.release){s*=v.release/double(releaseFrames);if(!--v.release)v.key=-1;}
                if(!std::isfinite(s)){s=0;v.key=-1;}
                v.last=s;++v.age;sum+=s;
            }
            out[2*i]=float(sum*left);out[2*i+1]=float(sum*right);
        }
    }
};
}
API int lf_abi(){return 1;}
API const char *lf_error(){return error.c_str();}
API void *lf_create(int rate,int model,int voices){
    try{
        if(rate!=44100||voices<1||voices>64)throw std::runtime_error("Unsupported sample rate or voice count");
        stk::Stk::showWarnings(false);stk::Stk::printErrors(false);
        return new Engine(model,voices);
    }catch(const std::exception &e){error=e.what();return nullptr;}
}
API void lf_free(void *p){delete static_cast<Engine*>(p);}
API int lf_control(void *p,int cc,double value){
    try{for(auto &v:static_cast<Engine*>(p)->voices)v.synth->controlChange(cc,value);return 0;}
    catch(const std::exception &e){error=e.what();return -1;}
}
API int lf_tone(void *p,double cutoff){
    if(!std::isfinite(cutoff)||cutoff<200||cutoff>16000)return -1;
    auto &e=*static_cast<Engine*>(p);e.cutoff=cutoff;
    for(auto &v:e.voices)if(v.key>=0)e.tone(v);
    return 0;
}
API int lf_event(void *p,int status,int a,int b){
    try{static_cast<Engine*>(p)->event(status,a,b);return 0;}
    catch(const std::exception &e){error=e.what();return -1;}
}
API int lf_render(void *p,float *out,int frames){
    try{if(frames<0||frames>65536)return -1;static_cast<Engine*>(p)->render(out,frames);return 0;}
    catch(const std::exception &e){error=e.what();return -1;}
}
