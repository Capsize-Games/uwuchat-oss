/**
 * Re-exported from UserSetupContext so existing import sites
 * continue to work unmodified.  The fetch/retry/poll logic runs
 * exactly once inside <UserSetupProvider> regardless of how many
 * components consume this hook.
 */
export {
  useUserSetup,
  type UserSetupState,
} from "../context/UserSetupContext";
