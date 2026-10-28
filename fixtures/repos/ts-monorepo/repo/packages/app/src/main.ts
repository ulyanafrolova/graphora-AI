import { Logger, add } from "@acme/ui";
import { Logger as RelLogger } from "../../ui/src";
import { helper } from "helper";

export const run = () => new Logger().write("info", String(add(1, 2))) ?? RelLogger ?? helper;
