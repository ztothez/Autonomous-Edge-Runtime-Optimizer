/* Phase 2: Runtime Configuration */
#include <zephyr/spinlock.h>

#include "config.h"

/* safe default */
static struct config_pkt cfg = { .sample_period_ms = 50 };
static struct k_spinlock cfg_lock;

struct config_pkt config_get(void)
{
    k_spinlock_key_t key = k_spin_lock(&cfg_lock);
    struct config_pkt c = cfg;
    k_spin_unlock(&cfg_lock, key);
    return c;
}

uint16_t config_sample_period_ms(void)
{
    return config_get().sample_period_ms;
}

bool config_validate(const struct config_pkt *c)
{
    return c->sample_period_ms >= PERIOD_MIN_MS &&
           c->sample_period_ms <= PERIOD_MAX_MS;
}

void config_set(const struct config_pkt *c)
{
    k_spinlock_key_t key = k_spin_lock(&cfg_lock);
    cfg = *c;
    k_spin_unlock(&cfg_lock, key);
}
