import React from "react";
import { User } from "../models";

function track(target: unknown) {}

@track
export class Button {
  render() {
    return <button>{new User("a").greet()}</button>;
  }
}
