# Shuttler ARTIQ Demo for Digilent Genesys2

## Requirements

You need to use ARTIQ, MiSoC and Migen with latest Digilent Genesys2 support.
Unitl it's merged, you can use Technosystem forks:

* [Migen, `genesys2_fix` branch](https://github.com/Technosystem-Labs/migen/tree/genesys2_fix)
* [MiSoC, `genesys2` branch](https://github.com/Technosystem-Labs/misoc/tree/genesys2)
* [ARTIQ, `genesys2` branch](https://github.com/Technosystem-Labs/artiq/tree/genesys2)

**Shuttler supports only `VADJ = 1.8V`. Make sure your carrier is configured 
properly!**

## Experiments

`shuttler_test_sine.py` - generates sine waves (samples pregenerated with sw)
of different frequencies.

Please remeber to add directory containing `shuttler_demo` to `PYTHONPATH` as 
there is a custom coredevice used.

## Building FW

`python -m python -m shuttler_demo.gateware.targets.genesys2`