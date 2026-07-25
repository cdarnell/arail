---
title: "Video Games"
id: world-video-games
name: "Video Games"
domain: video-games
version: "1.0.0"
tags: [world, knowledge, video-games]
when_to_use:
  - When the user asks about Video Games or its declared categories
  - When grounding a claim that falls inside this World's domain
when_not_to_use:
  - When the question is outside this World's declared categories
  - When a claim cannot be tied to one of this World's sourced terms (say so; don't invent)
---
This lab studies how games actually perform on real hardware: graphics settings and what they cost, GPU/CPU/RAM behavior, sim-racing feel, driver hygiene, and the metrics that decide a config (frame time, 1% lows, latency). Every factual claim is grounded in the World's cited sources. The method is measured autoresearch: change one variable, measure, keep the win. Unmeasured suggestions are labeled advice — this World never invents benchmark numbers.

Every term in this World is grounded in a cited source.

_Answer only from the terms below. Every term lists its source. If a question cannot be answered from these terms, say the World does not cover it — do not invent._

### Research method

- Change one variable at a time; measure; keep the win. A setting change without a measurement is a hypothesis, not a result.
- Respect the hardware envelope: never recommend past the user's stated GPU/VRAM/CPU/RAM or thermal limits.
- Read a game's tunables first — know the allowed values before proposing a change.
- Recommendations without a measurement are labeled advice, not results. Never state an FPS or benchmark figure that was not measured on the user's machine.
- Prefer frame-time consistency (1% lows, pacing) over average FPS when judging a config.

### Drivers

- **Clean Driver Install** (`clean-driver-install`) — Fully removing the previous GPU driver and its leftover files before installing a new one.
  - Source: authored
- **DirectX 12** (`directx-12`) — Microsoft's low-level graphics/compute API giving engines more direct control over the GPU than earlier DirectX versions.
  - Source: Microsoft DirectX 12 documentation (learn.microsoft.com)
- **Driver Rollback** (`driver-rollback`) — Reverting to a previously installed, known-good driver version after a new one causes problems.
  - Source: authored
- **Game Ready Driver** (`game-ready-driver`) — A driver release timed and optimized around a specific game's launch.
  - Source: NVIDIA Game Ready Driver documentation (nvidia.com/en-us/geforce/drivers)
- **GPU Driver** (`gpu-driver`) — The software layer that lets the OS and games talk to the GPU's hardware.
  - Source: Device driver (Wikipedia)
- **Shader Compilation** (`shader-compilation`) — Converting a game's shader code into GPU/driver-specific machine instructions before it can run.
  - Source: Shader (Wikipedia)
- **Vulkan** (`vulkan`) — Khronos Group's open, cross-platform, low-level graphics and compute API.
  - Source: Khronos Group Vulkan specification (khronos.org/vulkan)
- **WHQL** (`whql`) — Microsoft's certification program that a driver has passed a defined compatibility/stability test suite.
  - Source: Windows Hardware Compatibility Program (Microsoft documentation, learn.microsoft.com)

### Graphics Settings

- **Ambient Occlusion** (`ambient-occlusion`) — Approximates soft contact shadows where surfaces meet or crevices block ambient light.
  - Source: Ambient occlusion (Wikipedia)
- **Anisotropic Filtering** (`anisotropic-filtering`) — Sharpens textures viewed at oblique, shallow angles, like a road or floor stretching into the distance.
  - Source: Anisotropic filtering (Wikipedia)
- **Anti-Aliasing** (`anti-aliasing`) — Smoothing the jagged, stair-stepped edges that appear where diagonal or curved geometry meets a pixel grid.
  - Source: Spatial anti-aliasing (Wikipedia)
- **DLSS** (`dlss`) — NVIDIA's neural-network upscaler and frame-generation suite, exclusive to RTX GPUs.
  - Source: NVIDIA DLSS documentation (developer.nvidia.com/rtx/dlss)
- **Draw Distance** (`draw-distance`) — How far from the camera objects and terrain continue to be rendered before they're culled or faded.
  - Source: authored
- **Dynamic Resolution Scaling** (`dynamic-resolution-scaling`) — Automatically lowers render resolution under heavy GPU load to hold a target frame rate, then raises it back.
  - Source: Dynamic resolution (Wikipedia)
- **Field of View** (`field-of-view`) — How wide an angle of the game world the camera renders, usually set in degrees.
  - Source: Field of view in video games (PC Gaming Wiki)
- **Frame Generation** (`frame-generation`) — Inserting AI-generated interpolated frames between rendered frames to raise displayed frame rate.
  - Source: NVIDIA DLSS documentation (developer.nvidia.com/rtx/dlss); Motion interpolation (Wikipedia)
- **FreeSync** (`freesync`) — AMD's variable-refresh-rate brand, built on the open VESA Adaptive-Sync standard.
  - Source: AMD FreeSync documentation (amd.com/en/technologies/freesync)
- **FSR** (`fsr`) — AMD's open, vendor-agnostic spatial/temporal upscaler.
  - Source: AMD FidelityFX Super Resolution documentation (gpuopen.com)
- **FXAA** (`fxaa`) — A cheap post-process filter that blurs detected edges after the frame is already rendered.
  - Source: Fast approximate anti-aliasing (Wikipedia)
- **G-SYNC** (`g-sync`) — NVIDIA's variable-refresh-rate certification and (on some panels) dedicated hardware module.
  - Source: NVIDIA G-SYNC documentation (nvidia.com/en-us/geforce/products/g-sync)
- **Level of Detail** (`level-of-detail`) — Swapping a distant object's mesh for a simpler version to save rendering cost.
  - Source: Level of detail (computer graphics) (Wikipedia)
- **MSAA** (`msaa`) — Anti-aliasing that samples geometry edges multiple times per pixel without re-shading the whole pixel.
  - Source: Multisample anti-aliasing (Wikipedia)
- **Path Tracing** (`path-tracing`) — A more complete, fully ray-traced lighting model that simulates the full global-illumination light path.
  - Source: Path tracing (Wikipedia)
- **Ray Tracing** (`ray-tracing`) — Simulating light paths (reflection, shadows, global illumination) by tracing rays instead of rasterizing approximations.
  - Source: Ray tracing (graphics) (Wikipedia)
- **Render Resolution** (`render-resolution`) — The pixel grid a frame is actually drawn at, before any upscaling or display scaling.
  - Source: authored
- **Shadow Quality** (`shadow-quality`) — The resolution and draw distance of shadow maps, and how many cascades cover the scene.
  - Source: authored
- **TAA** (`taa`) — Anti-aliasing that blends motion-compensated data from previous frames into the current one.
  - Source: Temporal anti-aliasing (Wikipedia)
- **Texture Quality** (`texture-quality`) — The resolution and mip level of surface textures loaded into VRAM.
  - Source: authored
- **Upscaling** (`upscaling`) — Reconstructing a higher-resolution image from a lower-resolution render using temporal or spatial data.
  - Source: Image scaling (Wikipedia); Super-resolution imaging (Wikipedia)
- **Variable Refresh Rate** (`variable-refresh-rate`) — The display refreshes exactly when a new frame is ready, instead of at a fixed interval.
  - Source: Variable refresh rate (Wikipedia)
- **V-Sync** (`vsync`) — Synchronizes frame delivery to the display's refresh cycle to prevent screen tearing.
  - Source: Screen tearing (Wikipedia); Vertical blanking interval (Wikipedia)
- **XeSS** (`xess`) — Intel's neural upscaler, with an accelerated path on Arc GPUs and a fallback path elsewhere.
  - Source: Intel Xe Super Sampling (XeSS) documentation (intel.com)

### Hardware

- **CPU** (`cpu`) — The general-purpose processor that runs game logic, physics, AI, and issues draw calls to the GPU.
  - Source: Central processing unit (Wikipedia)
- **CPU Bottleneck** (`cpu-bottleneck`) — A performance ceiling set by the CPU rather than the GPU — lowering graphics settings won't help.
  - Source: Bottlenecking (PC Gaming Wiki)
- **DirectStorage** (`directstorage`) — A Windows API letting game assets stream from NVMe storage directly toward the GPU, bypassing much of the traditional CPU-mediated path.
  - Source: Microsoft DirectStorage documentation (learn.microsoft.com)
- **GPU** (`gpu`) — The massively parallel processor that rasterizes or ray-traces frames and runs modern graphics/AI workloads.
  - Source: Graphics processing unit (Wikipedia)
- **GPU-Bound** (`gpu-bound`) — A performance ceiling set by the GPU rather than the CPU — lowering graphics settings will raise frame rate.
  - Source: Bottlenecking (PC Gaming Wiki)
- **Monitor Refresh Rate** (`monitor-refresh-rate`) — How many times per second a display redraws its image, measured in hertz.
  - Source: Refresh rate (Wikipedia)
- **RAM** (`ram`) — The CPU's working memory, holding the game's loaded assets, world state, and code in flight.
  - Source: Random-access memory (Wikipedia)
- **RAM Timings** (`ram-timings`) — The wait-cycle counts (CAS latency and related delays) that govern how quickly RAM responds to a request.
  - Source: Memory timings (Wikipedia)
- **Resizable BAR** (`resizable-bar`) — Lets the CPU address the GPU's full VRAM at once instead of in small windows, reducing overhead for some workloads.
  - Source: PCI-SIG PCI Express Resizable BAR Capability specification; AMD Smart Access Memory documentation (amd.com)
- **TDP** (`tdp`) — The amount of heat a cooling solution must be designed to dissipate for a given chip.
  - Source: Thermal design power (Wikipedia)
- **Thermal Throttling** (`thermal-throttling`) — A CPU or GPU automatically lowers its clock speed to stay under its temperature limit.
  - Source: Dynamic frequency scaling / thermal management (Wikipedia)
- **VRAM** (`vram`) — The dedicated memory on a GPU that holds textures, frame buffers, and other rendering data.
  - Source: Video RAM (Wikipedia)
- **XMP** (`xmp`) — A stored memory profile that lets RAM run at its rated speed/timings instead of a conservative default.
  - Source: Extreme Memory Profile (Wikipedia)

### Performance Metrics

- **Benchmark** (`benchmark`) — A repeatable, controlled test run used to measure and compare performance under identical conditions.
  - Source: Benchmark (computing) (Wikipedia)
- **FPS** (`fps`) — How many complete frames are rendered and displayed each second, usually reported as an average.
  - Source: Frame rate (Wikipedia)
- **Frame Pacing** (`frame-pacing`) — How evenly spaced frame deliveries are in time, independent of the average frame rate.
  - Source: authored
- **Frame Time** (`frame-time`) — How long, in milliseconds, each individual frame took to render — the raw data average FPS is computed from.
  - Source: authored
- **Input Latency** (`input-latency`) — The delay between a physical input action and its visible effect on screen.
  - Source: Input lag (Wikipedia)
- **Micro-Stutter** (`micro-stutter`) — Brief, small, repeated interruptions in frame delivery that are individually subtle but collectively feel rough.
  - Source: authored
- **NVIDIA Reflex** (`nvidia-reflex`) — NVIDIA's technology for reducing render-queue-related input latency, and a companion measurement tool.
  - Source: NVIDIA Reflex documentation (nvidia.com/en-us/geforce/technologies/reflex)
- **1% Lows** (`one-percent-lows`) — The average frame rate across the slowest 1% of frames in a session — a stutter-sensitive companion metric to average FPS.
  - Source: Frame time percentile / '1% low' benchmarking methodology (Gamers Nexus, TechPowerUp methodology articles)
- **PresentMon** (`presentmon`) — An open-source tool that captures precise, per-frame timing data directly from the OS's presentation pipeline.
  - Source: Intel PresentMon documentation/repository (github.com/GameTechDev/PresentMon)
- **Shader Compilation Stutter** (`shader-compilation-stutter`) — A frame-time spike caused by compiling a shader on the spot, the first time it's needed.
  - Source: authored
- **System Latency** (`system-latency`) — The full end-to-end delay across every stage from input device to photons leaving the display.
  - Source: authored
- **0.1% Lows** (`zero-point-one-percent-lows`) — The average frame rate across the slowest 0.1% of frames — a stricter, spike-sensitive companion to 1% lows.
  - Source: Frame time percentile / '0.1% low' benchmarking methodology (Gamers Nexus, TechPowerUp methodology articles)

### Sim Racing

- **Direct Drive Wheel** (`direct-drive-wheel`) — A wheel driven directly by a high-torque motor, with no belt, gear, or pulley between motor and wheel.
  - Source: authored
- **FFB Clipping** (`ffb-clipping`) — The wheel's motor hits its output ceiling and can no longer represent forces above that point.
  - Source: authored
- **Force Feedback** (`force-feedback`) — Motorized resistance and vibration through a wheel that communicates road surface, grip, and load.
  - Source: Force feedback (Wikipedia)
- **Load Cell Pedal** (`load-cell-pedal`) — A brake pedal that measures the force applied, rather than how far the pedal physically travels.
  - Source: Load cell (Wikipedia)
- **Pedal Calibration** (`pedal-calibration`) — Mapping a pedal's physical input range to the game's expected 0–100% input range.
  - Source: authored
- **Sim Racing** (`sim-racing`) — Racing games built around physically modeled vehicle dynamics rather than arcade-style handling.
  - Source: Sim racing (Wikipedia)
- **Slip Angle** (`slip-angle`) — The angle between where a tire is pointed and the direction it's actually traveling.
  - Source: Slip angle (Wikipedia)
- **Steering Rotation** (`steering-rotation`) — How many degrees the wheel physically turns lock-to-lock, matched to the car being driven in-sim.
  - Source: authored
- **Telemetry** (`telemetry`) — Recorded, time-stamped vehicle data (speed, throttle, brake pressure, tire grip, and more) captured during a lap.
  - Source: authored
- **Tire Model** (`tire-model`) — The physics model that computes tire grip, slip, and force as a function of load, angle, and surface.
  - Source: Pacejka Magic Formula / tire model (Wikipedia: 'Vehicle dynamics', 'Slip angle')
- **Triple Screen** (`triple-screen`) — Three monitors arranged to extend peripheral field of view for a wraparound cockpit view.
  - Source: authored
- **Wheel Base** (`wheel-base`) — The motor-and-electronics unit that drives the wheel rim; separate from the pedals and rim itself.
  - Source: authored

<!-- dac:world_sha256 dae307da72c039c99af680f6b0f744e21a37d9de75bf79c7f6bfb46ab8ec2bb2 -->
