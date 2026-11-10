/* Drives the matiec-generated PLC code scan by scan, like OpenPLC's runtime. */
#include <stdio.h>
#include <stdlib.h>
#include "iec_types_all.h"
#include "POUS.h"
#include "Config0.h"

/* Storage + pointers for located variables (what OpenPLC's glueVars does). */
#define __LOCATED_VAR(type, name, ...) type __##name##_val; type *name = &__##name##_val;
#include "LOCATED_VARIABLES.h"
#undef __LOCATED_VAR

TIME __CURRENT_TIME;
BOOL __DEBUG;
extern unsigned long long common_ticktime__;
static unsigned long tick = 0;
static int fails = 0;

static void scan(int level) { *__MW0 = level; config_run__(tick++); }

static void check(const char *what, int level, int pump, int hi, int lo, int trip) {
    int ok = *__QX0_0 == pump && *__QX0_1 == hi && *__QX0_2 == lo && *__QX0_3 == trip;
    printf("%-4s lvl=%4d pump=%d hi=%d lo=%d trip=%d reset=%d  %s\n", ok ? "ok" : "FAIL",
           level, *__QX0_0, *__QX0_1, *__QX0_2, *__QX0_3, *__QX0_4, what);
    if (!ok) fails++;
}
#define STEP(lvl, p, h, l, t, what) do { scan(lvl); check(what, lvl, p, h, l, t); } while (0)

int main(void) {
    config_init__();
    STEP(500, 0,0,0,0, "start mid-band: pump off");
    STEP(700, 0,0,0,0, "exactly 70%: not > 70, still off");
    STEP(701, 1,0,0,0, "above 70%: pump on");
    STEP(500, 1,0,0,0, "back in band: stays on (hysteresis)");
    STEP(300, 1,0,0,0, "exactly 30%: still on");
    STEP(299, 0,0,0,0, "below 30%: pump off");
    STEP(500, 0,0,0,0, "in band from below: stays off");
    STEP(150, 0,0,1,0, "15%: LO alarm");
    STEP(151, 0,0,0,0, "15.1%: LO clears");
    STEP(849, 1,0,0,0, "84.9%: no HI yet");
    STEP(850, 1,1,0,0, "85%: HI alarm");
    STEP(950, 1,1,0,1, "95%: HIHI trip latches");
    *__QX0_4 = 1;
    STEP(960, 1,1,0,1, "reset while >=95%: ignored");
    if (*__QX0_4) { puts("FAIL reset coil not self-cleared"); fails++; }
    STEP(100, 1,0,1,1, "10%: trip still latched, pump forced on");
    *__QX0_3 = 0; *__QX0_0 = 0;  /* external Modbus write tries to clear trip + stop pump */
    STEP(100, 1,0,1,1, "external coil writes overwritten next scan");
    *__QX0_4 = 1;
    STEP(100, 0,0,1,0, "reset below 95%: trip clears, pump off (<30%)");
    if (*__QX0_4) { puts("FAIL reset coil not self-cleared"); fails++; }
    STEP(950, 1,1,0,1, "trip can latch again");
    printf("\n%s (%d failures)\n", fails ? "FAILED" : "ALL PASSED", fails);
    return fails != 0;
}
