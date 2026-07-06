import type {
  AppRuntimeProfile,
  RuntimeProfileDto
} from "../../domain/runtime/AppRuntimeProfile";

export interface RuntimeProfileRepository {
  load(): Promise<AppRuntimeProfile>;
}

export class LoadAppRuntimeProfile {
  public constructor(private readonly runtimeProfileRepository: RuntimeProfileRepository) {}

  public async load(): Promise<RuntimeProfileDto> {
    const runtimeProfile = await this.runtimeProfileRepository.load();

    return runtimeProfile.toDto();
  }
}
