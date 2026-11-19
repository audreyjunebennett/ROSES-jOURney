package roses.axiomgate.mixin;

import roses.axiomgate.RosesCreative;

import com.moulberry.axiom.AxiomServer;
import com.moulberry.axiom.restrictions.AxiomPermission;
import com.moulberry.axiom.restrictions.AxiomPermissionSet;
import com.moulberry.axiom.restrictions.Restrictions;
import net.minecraft.server.level.ServerPlayer;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

@Mixin(value = AxiomServer.class, remap = false)
abstract class AxiomServerMixin {
    @Inject(method = "hasPermission", at = @At("HEAD"), cancellable = true)
    private static void roses$gateActions(ServerPlayer player, AxiomPermission permission,
                                        CallbackInfoReturnable<Boolean> result) {
        if (!RosesCreative.inCreative(player) && !RosesCreative.survivalAxiomEnabled(player)) {
            result.setReturnValue(false);
        }
    }

    @Inject(method = "getPermissions", at = @At("HEAD"), cancellable = true)
    private static void roses$gatePermissionSet(ServerPlayer player,
                                               CallbackInfoReturnable<AxiomPermissionSet> result) {
        if (RosesCreative.survivalAxiomEnabled(player)
                || (RosesCreative.inCreative(player) && RosesCreative.canEnter(player))) {
            result.setReturnValue(AxiomPermissionSet.ALL);
        } else if (!RosesCreative.inCreative(player)) {
            result.setReturnValue(AxiomPermissionSet.NONE);
        }
    }

    @Inject(method = "calculateRestrictions", at = @At("HEAD"), cancellable = true)
    private static void roses$sendDisabledRestrictions(ServerPlayer player,
                                                       CallbackInfoReturnable<Restrictions> result) {
        if (!RosesCreative.inCreative(player) && !RosesCreative.survivalAxiomEnabled(player)) {
            Restrictions disabled = new Restrictions();
            disabled.allowedPermissions.clear();
            disabled.deniedPermissions.addAll(java.util.EnumSet.allOf(AxiomPermission.class));
            result.setReturnValue(disabled);
        }
    }
}
