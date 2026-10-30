/***************************************************/
/*! \class FileLoop
    \brief STK file looping / oscillator class.

    This class provides audio file looping functionality.  Any audio
    file that can be loaded by FileRead can be looped using this
    class.

    FileLoop supports multi-channel data.  It is important to
    distinguish the tick() method that computes a single frame (and
    returns only the specified sample of a multi-channel frame) from
    the overloaded one that takes an StkFrames object for
    multi-channel and/or multi-frame data.

    by Perry R. Cook and Gary P. Scavone, 1995--2023.
*/
/***************************************************/

#include "FileLoop.h"
#include <cmath>
#include <algorithm>
#include "oscillators.h"

namespace stk {

FileLoop :: FileLoop( unsigned long chunkThreshold, unsigned long chunkSize )
  : FileWvIn( chunkThreshold, chunkSize ), phaseOffset_(0.0)
{
  Stk::addSampleRateAlert( this );
}

FileLoop :: FileLoop( std::string fileName, bool raw, bool doNormalize,
                      unsigned long chunkThreshold, unsigned long chunkSize,
                      bool doInt2FloatScaling )
  : FileWvIn( chunkThreshold, chunkSize ), phaseOffset_(0.0)
{
  this->openFile( fileName, raw, doNormalize, doInt2FloatScaling );
  Stk::addSampleRateAlert( this );
}

FileLoop :: ~FileLoop( void )
{
  Stk::removeSampleRateAlert( this );
}

void FileLoop :: openFile( std::string fileName, bool raw, bool doNormalize, bool doInt2FloatScaling )
{
  const bool sine = fileName.find("sinewave.raw") != std::string::npos;
  const short *wave = sine ? sinewave : fwavblnk;
  fileSize_ = sine ? sizeof(sinewave)/sizeof(short) : sizeof(fwavblnk)/sizeof(short);
  chunking_=false;data_.resize(fileSize_+1,1);lastFrame_.resize(1,1);
  double peak=1;for(unsigned i=0;i<fileSize_;++i)peak=std::max(peak,std::abs(double(wave[i])));
  for(unsigned i=0;i<fileSize_;++i)data_[i]=wave[i]/peak;
  data_[fileSize_]=data_[0];setRate(1);reset();
}

void FileLoop :: setRate( StkFloat rate )
{
  rate_ = rate;

  if ( fmod( rate_, 1.0 ) != 0.0 ) interpolate_ = true;
  else interpolate_ = false;
}

void FileLoop :: addTime( StkFloat time )
{
  // Add an absolute time in samples.
  time_ += time;

  while ( time_ < 0.0 )
    time_ += fileSize_;
  while ( time_ >= fileSize_ )
    time_ -= fileSize_;
}

void FileLoop :: addPhase( StkFloat angle )
{
  // Add a time in cycles (one cycle = fileSize).
  time_ += fileSize_ * angle;

  while ( time_ < 0.0 )
    time_ += fileSize_;
  while ( time_ >= fileSize_ )
    time_ -= fileSize_;
}

void FileLoop :: addPhaseOffset( StkFloat angle )
{
  // Add a phase offset in cycles, where 1.0 = fileSize.
  phaseOffset_ = fileSize_ * angle;
}

StkFloat FileLoop :: tick( unsigned int channel )
{
#if defined(_STK_DEBUG_)
  if ( channel >= data_.channels() ) {
    oStream_ << "FileLoop::tick(): channel argument and soundfile data are incompatible!";
    handleError( StkError::FUNCTION_ARGUMENT );
  }
#endif

  if ( finished_ ) return 0.0;

  // Check limits of time address ... if necessary, recalculate modulo
  // fileSize.
  while ( time_ < 0.0 )
    time_ += fileSize_;
  while ( time_ >= fileSize_ )
    time_ -= fileSize_;

  StkFloat tyme = time_;
  if ( phaseOffset_ ) {
    tyme += phaseOffset_;
    while ( tyme < 0.0 )
      tyme += fileSize_;
    while ( tyme >= fileSize_ )
      tyme -= fileSize_;
  }

  if ( chunking_ ) {

    // Check the time address vs. our current buffer limits.
    if ( ( time_ < (StkFloat) chunkPointer_ ) ||
         ( time_ > (StkFloat) ( chunkPointer_ + chunkSize_ - 1 ) ) ) {

      while ( time_ < (StkFloat) chunkPointer_ ) { // negative rate
        chunkPointer_ -= chunkSize_ - 1; // overlap chunks by one frame
        if ( chunkPointer_ < 0 ) chunkPointer_ = 0;
      }
      while ( time_ > (StkFloat) ( chunkPointer_ + chunkSize_ - 1 ) ) { // positive rate
        chunkPointer_ += chunkSize_ - 1; // overlap chunks by one frame
        if ( chunkPointer_ + chunkSize_ > fileSize_ ) { // at end of file
          chunkPointer_ = fileSize_ - chunkSize_ + 1; // leave extra frame at end of buffer
          // Now fill extra frame with first frame data.
          for ( unsigned int j=0; j<firstFrame_.channels(); j++ )
            data_( data_.frames() - 1, j ) = firstFrame_[j];
        }
      }

      // Load more data.
      file_.read( data_, chunkPointer_, int2floatscaling_ );
    }

    // Adjust index for the current buffer.
    tyme -= chunkPointer_;
  }

  if ( interpolate_ ) {
    for ( unsigned int i=0; i<lastFrame_.size(); i++ )
      lastFrame_[i] = data_.interpolate( tyme, i );
  }
  else {
    for ( unsigned int i=0; i<lastFrame_.size(); i++ )
      lastFrame_[i] = data_( (size_t) tyme, i );
  }

  // Increment time, which can be negative.
  time_ += rate_;

  return lastFrame_[channel];
}

StkFrames& FileLoop :: tick( StkFrames& frames, unsigned int channel)
{
  if ( finished_ ) {
#if defined(_STK_DEBUG_)
    oStream_ << "FileLoop::tick(): no file data is loaded!";
    handleError( StkError::DEBUG_PRINT );
#endif
  return frames;
  }
        
  unsigned int nChannels = lastFrame_.channels();
#if defined(_STK_DEBUG_)
  if ( channel > frames.channels() - nChannels ) {
    oStream_ << "FileLoop::tick(): channel and StkFrames arguments are incompatible!";
    handleError( StkError::FUNCTION_ARGUMENT );
  }
#endif
        
  StkFloat *samples = &frames[channel];
  unsigned int j, hop = frames.channels() - nChannels;
  if ( nChannels == 1 ) {
  for ( unsigned int i=0; i<frames.frames(); i++, samples += hop )
    *samples++ = tick();
  }
  else {
    for ( unsigned int i=0; i<frames.frames(); i++, samples += hop ) {
      *samples++ = tick();
      for ( j=1; j<nChannels; j++ )
        *samples++ = lastFrame_[j];
      }
    }
  return frames;
        
}

} // stk namespace
