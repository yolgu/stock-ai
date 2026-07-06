import { AppRuntimeProfile } from "../../domain/runtime/AppRuntimeProfile";
import type { RuntimeProfileRepository } from "./LoadAppRuntimeProfile";

export class DefaultRuntimeProfileRepository implements RuntimeProfileRepository {
  public async load(): Promise<AppRuntimeProfile> {
    return AppRuntimeProfile.createDefault();
  }
}
