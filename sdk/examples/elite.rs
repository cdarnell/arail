use nucleus_sdk::prelude::*;

fn main() {
    // Check the "Heartbeat" of the lab
    let status = Heart::check_health();
    println!("Lab healthy: {}", status.healthy);

    // Command the Janitor (ZeroClaw)
    Janitor::repair_service("llm-gateway");

    // Calculate the "Power vs Cloud" delta for the current task
    let efficiency = Power::get_efficiency_report();
    println!("Lab Savings: ${}", efficiency.savings);
}
