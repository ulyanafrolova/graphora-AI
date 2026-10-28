export class User {
  constructor(public name: string) {}
  greet(): string {
    return this.name;
  }
}

export enum Role {
  Admin,
}
