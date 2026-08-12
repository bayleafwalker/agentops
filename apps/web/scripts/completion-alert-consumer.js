import { CompletionAlertConsumer } from "../lib/cockpit/completion-alerts.js";

const consumer = new CompletionAlertConsumer();

function stop(signal) {
  consumer.stop();
  process.exitCode = 0;
  process.stderr.write(`completion-alert-consumer: stopped (${signal})\n`);
}

process.on("SIGINT", () => stop("SIGINT"));
process.on("SIGTERM", () => stop("SIGTERM"));

process.stderr.write("completion-alert-consumer: starting bounded cursor poller\n");
consumer.start();
