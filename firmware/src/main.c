/* EdgeOpt firmware: main loop only.
 * Sampling and processing live in sensors/ and dsp/, configuration in config/,
 * BLE in ble/. */
#include <stdio.h>
#include <zephyr/kernel.h>
#include <cmsis_core.h>

#include "sensors/sensor.h"
#include "dsp/features.h"
#include "config/config.h"
#include "ble/ble_svc.h"

#define N_MAX         128
#define WINDOW        16
#define EVENT_RMS_MG  50
#define CPU_MHZ       64U      /* nRF52833 core clock, DWT cycle counter */

static int32_t buf[N_MAX];
static uint16_t n;

/* Cycle counter used to measure processing time (k_cycle_get_32 only ticks at 32 kHz). */
static void dwt_init(void)
{
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

int main(void)
{
    if (ble_svc_init() != 0) {
        return 0;
    }

    k_msleep(500);
    sensor_i2c_scan();
    sensor_init();
    dwt_init();

    uint32_t events = 0;
    bool above_prev = false;
    struct telemetry_pkt pkt = {0};
    int64_t next = k_uptime_get();

    uint32_t busy_us = 0;                         /* CPU-busy time in the current window */
    uint32_t win_start_ms = k_uptime_get_32();

    while (1) {
        uint32_t b0 = DWT->CYCCNT;                /* start of this iteration's work */

        /* ---- Phase 1: Embedded Baseline - windowed RMS feature + processing time ---- */
        int32_t mg = sensor_read_mg();
        buf[n++] = mg;

        if (n >= WINDOW) {
            uint32_t c0 = DWT->CYCCNT;
            uint32_t rms = window_rms(buf, n);
            uint32_t us = (DWT->CYCCNT - c0) / CPU_MHZ;

            bool above = rms > EVENT_RMS_MG;
            if (above && !above_prev) {                /* rising edge = one new event */
                events++;
                printf("EVENT: rms %u mg  events %u\n", rms, events);
            }
            above_prev = above;

            printf("rms %u mg  proc %u us\n", rms, us);
            n = 0;

            /* ---- Phase 1: CPU-load proxy = busy time / elapsed time, in permille ---- */
            uint32_t elapsed_ms = k_uptime_get_32() - win_start_ms;
            pkt.duty_permille = elapsed_ms ? busy_us / elapsed_ms : 0;
            busy_us = 0;
            win_start_ms = k_uptime_get_32();

            /* ---- Phase 1: telemetry packet assembly ---- */
            pkt.rms_mg = rms;
            pkt.proc_us = us;
            pkt.events = events;
            pkt.period_ms = config_sample_period_ms();
            pkt.windows++;
            pkt.uptime_ms = k_uptime_get_32();

            /* ---- Phase 1: BLE telemetry out (one report per window) ---- */
            if (ble_svc_subscribed()) {
                if (ble_svc_notify(&pkt) == 0) {
                    pkt.sent++;
                } else {
                    pkt.notify_err++;
                }
                pkt.seq++;
            }
        }

        busy_us += (DWT->CYCCNT - b0) / CPU_MHZ;       /* work done this iteration, before sleeping */

        next += config_sample_period_ms();
        k_sleep(K_TIMEOUT_ABS_MS(next));
    }
}