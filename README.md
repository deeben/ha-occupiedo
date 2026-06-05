# Occupiedo 🏠🕵️‍♂️

**Occupiedo** is a smart, zero-configuration presence simulation integration for Home Assistant. 

Unlike typical simulators that rely on rigid, pre-programmed schedules, Occupiedo learns the actual history of your devices to mimic realistic human activity when you're away.

---

## Features

- **🧠 Smart History Learning**: Queries your Home Assistant history database over the last 7 days to calculate the average turn-on and turn-off times for each device.
- **🎲 Dynamic Random Jitter**: Applies a $\pm 20$-minute daily randomization offset to the learned times, ensuring the simulation never repeats at the exact same minute.
- **⚡ Zero-Configuration Setup**: No complex scheduling YAML, sliders, or timing parameters. Just give your simulation profile a name and select your target entities.
- **🩹 Self-Healing / Catch-up Logic**: Turning the switch ON mid-evening instantly catches up—evaluating which lights should be on at the current time, setting their states, and scheduling the remaining turn-off events.
- **🔄 Midnight Rollover**: Recalculates and schedules the next day's randomized timings automatically every night at midnight.
- **🔌 Clean Switch Control**: Provides a simple switch helper for each profile. Turning it ON runs the simulation. Turning it OFF instantly cancels all schedules and turns the simulated lights off.
- **🚀 Performance Optimized**: Executes all history database queries asynchronously in the background using Home Assistant's executor pool to prevent event loop bottlenecks.

---

## How It Works

1. **Active Evening Window**: Occupiedo analyzes state history daily between **16:00 (4:00 PM)** and **23:59 (11:59 PM)**.
2. **First-On, Last-Off Filtering**:
   - For each day in the last week, it extracts the first transition to `"on"` (the typical evening turn-on time) and the last transition from `"on"` (the typical bedtime turn-off time).
3. **Time Averaging**: It averages these times to determine the baseline. If a device has no history (e.g. newly added, or was unused last week), it falls back to a default schedule: **ON at 19:00** and **OFF at 22:00**.
4. **Daily Random Scheduling**: Every day, a target schedule is computed as `average_time ± random(-20, 20) minutes`, clamped securely within the active window boundaries.

---

## Setup & Installation

### 1. Installation via HACS
1. Open HACS in Home Assistant.
2. Click the three dots in the top-right corner and select **Custom repositories**.
3. Add `https://github.com/deeben/ha-occupiedo` with Category **Integration**.
4. Click **Download**.
5. Restart Home Assistant.

### 2. Configure a Profile
1. Go to **Settings > Devices & Services > Add Integration**.
2. Search for **Occupiedo** (or refresh your browser cache if it doesn't appear).
3. Set the **Profile Name** (e.g., `Upstairs Simulation`).
4. Select the **Controlled Entities** to simulate.
5. Click **Submit**. 

This creates a new switch (`switch.nothomealone_<profile_name>`). Simply turn this switch ON when leaving your home to start the presence simulation!
