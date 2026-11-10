(*
  tank_control.st  -  ics-security-lab water tank controller (OpenPLC_v3)

  Level comes from the simulator as an INT 0..1000 (= 0.0..100.0 %).
  All thresholds below are in those raw units (tenths of a percent).

  Control:
    - Pump ON  when level > 70 %, OFF when level < 30 % (hysteresis band,
      so the pump doesn't chatter around a single setpoint).
    - HI alarm   at >= 85 %, LO alarm at <= 15 %   (non-latching).
    - HIHI trip  at >= 95 %: latches and forces the pump ON until an
      operator reset. The reset is only accepted once the level is back
      below 95 %; otherwise it is ignored and the trip stays latched.

  Modbus map (OpenPLC_v3 fixed mapping, see docs/architecture.md):
    %MW0   holding register 1024  level_raw   simulator -> PLC
    %QX0.0 coil 0                 pump        PLC -> simulator
    %QX0.1 coil 1                 alarm_hi    PLC -> HMI
    %QX0.2 coil 2                 alarm_lo    PLC -> HMI
    %QX0.3 coil 3                 trip_hihi   PLC -> HMI (latched status)
    %QX0.4 coil 4                 op_reset    HMI -> PLC (momentary)

  Note: every %QX coil is writable over Modbus. Outputs are therefore
  recomputed from internal state every scan, so a stray external write
  to pump/alarm/trip coils is overwritten on the next scan.
*)

PROGRAM tank_control
  VAR
    (* ---- Process I/O, exchanged over Modbus ---- *)
    level_raw AT %MW0   : INT;   (* tank level, 0..1000 *)
    pump      AT %QX0.0 : BOOL;  (* pump run command *)
    alarm_hi  AT %QX0.1 : BOOL;  (* level >= 85 % *)
    alarm_lo  AT %QX0.2 : BOOL;  (* level <= 15 % *)
    trip_hihi AT %QX0.3 : BOOL;  (* HIHI trip active (latched) *)
    op_reset  AT %QX0.4 : BOOL;  (* operator reset pushbutton *)
  END_VAR

  VAR
    (* ---- Internal state (not reachable over Modbus) ---- *)
    pump_demand  : BOOL := FALSE;  (* hysteresis controller output *)
    trip_latched : BOOL := FALSE;  (* the real HIHI latch *)
  END_VAR

  VAR CONSTANT
    PUMP_ON_LEVEL  : INT := 700;   (* 70 % *)
    PUMP_OFF_LEVEL : INT := 300;   (* 30 % *)
    HI_LEVEL       : INT := 850;   (* 85 % *)
    LO_LEVEL       : INT := 150;   (* 15 % *)
    HIHI_LEVEL     : INT := 950;   (* 95 % *)
  END_VAR

  (* 1. HIHI trip: set the latch whenever the level reaches the trip point. *)
  IF level_raw >= HIHI_LEVEL THEN
    trip_latched := TRUE;
  END_IF;

  (* 2. Operator reset. Acts like a momentary pushbutton: the PLC clears
        the coil after reading it, so the operator only has to write TRUE.
        A reset while the level is still >= 95 % is ignored. *)
  IF op_reset THEN
    IF level_raw < HIHI_LEVEL THEN
      trip_latched := FALSE;
    END_IF;
    op_reset := FALSE;
  END_IF;

  (* 3. Hysteresis control. Between the two setpoints pump_demand keeps
        its previous value, which is what creates the deadband. *)
  IF level_raw > PUMP_ON_LEVEL THEN
    pump_demand := TRUE;
  ELSIF level_raw < PUMP_OFF_LEVEL THEN
    pump_demand := FALSE;
  END_IF;

  (* 4. Drive outputs from internal state every scan. The trip overrides
        normal control and keeps the pump running. *)
  pump      := pump_demand OR trip_latched;
  trip_hihi := trip_latched;
  alarm_hi  := level_raw >= HI_LEVEL;
  alarm_lo  := level_raw <= LO_LEVEL;
END_PROGRAM


CONFIGURATION Config0
  RESOURCE Res0 ON PLC
    TASK MainTask(INTERVAL := T#20ms, PRIORITY := 0);
    PROGRAM Inst0 WITH MainTask : tank_control;
  END_RESOURCE
END_CONFIGURATION
