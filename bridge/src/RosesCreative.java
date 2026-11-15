package roses.axiomgate;

import com.mojang.brigadier.exceptions.CommandSyntaxException;
import dev.wroud.mc.worlds.McWorld;
import dev.wroud.mc.worlds.manager.WorldsException;
import dev.wroud.mc.worlds.manager.group.WorldGroups;
import net.fabricmc.api.DedicatedServerModInitializer;
import net.fabricmc.fabric.api.attachment.v1.AttachmentRegistry;
import net.fabricmc.fabric.api.attachment.v1.AttachmentTarget;
import net.fabricmc.fabric.api.attachment.v1.AttachmentType;
import net.fabricmc.fabric.api.command.v2.CommandRegistrationCallback;
import net.luckperms.api.LuckPermsProvider;
import net.luckperms.api.model.user.User;
import net.luckperms.api.query.QueryOptions;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.core.registries.Registries;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.Identifier;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.level.portal.TeleportTransition;
import net.minecraft.world.phys.Vec2;
import net.minecraft.world.phys.Vec3;

import java.util.Optional;

import static net.minecraft.commands.Commands.literal;

public final class RosesCreative implements DedicatedServerModInitializer {
    private static final Identifier CREATIVE = Identifier.fromNamespaceAndPath("roses", "expansive_fantasy");
    private static final Identifier ORIGINAL_CREATIVE = Identifier.fromNamespaceAndPath("roses", "creative");
    private static final Identifier SURVIVAL = Identifier.withDefaultNamespace("overworld");
    private static final String ACCESS = "roses.creative.access";
    private static final AttachmentType<ServerPlayer.SavedPosition> SURVIVAL_RETURN =
        AttachmentRegistry.create(Identifier.fromNamespaceAndPath("roses", "survival_return"), builder ->
            builder.persistent(ServerPlayer.SavedPosition.MAP_CODEC.codec()).copyOnDeath());

    public static boolean inCreative(ServerPlayer player) {
        var dimension = player.level().dimension().identifier();
        return dimension.equals(CREATIVE) || dimension.equals(ORIGINAL_CREATIVE);
    }

    public static boolean canEnter(ServerPlayer player) {
        // Worlds replaces the ServerPlayer on a group switch. Look up the account
        // directly so access does not depend on data attached to the old entity.
        User user = LuckPermsProvider.get().getUserManager().getUser(player.getUUID());
        return user != null && user.getCachedData().getPermissionData(QueryOptions.nonContextual())
            .checkPermission(ACCESS).asBoolean();
    }

    @Override
    public void onInitializeServer() {
        CommandRegistrationCallback.EVENT.register((dispatcher, context, environment) ->
            dispatcher.register(literal("roses")
                .then(literal("creative")
                    .requires(source -> source.getEntity() instanceof ServerPlayer player && canEnter(player))
                    .executes(contextNode -> enterCreative(contextNode.getSource())))
                .then(literal("survival")
                    .requires(source -> source.getEntity() instanceof ServerPlayer player && inCreative(player))
                    .executes(contextNode -> returnToSurvival(contextNode.getSource())))));
    }

    private static int enterCreative(CommandSourceStack source) throws CommandSyntaxException {
        var player = source.getPlayerOrException();
        var server = source.getServer();
        var level = server.getLevel(ResourceKey.create(Registries.DIMENSION, CREATIVE));
        if (level == null) {
            return travel(source, CREATIVE);
        }
        if (player.level() == level || player.isDeadOrDying()) {
            return 0;
        }

        // Lazy worlds publish Fabric's level-load event before becoming ready.
        // Distant Horizons needs that event before receiving a player-level change.
        var ready = McWorld.whenReady(level);
        if (ready.isCompletedExceptionally()) {
            source.sendFailure(Component.literal("The Creative world could not load."));
            return 0;
        }
        if (!ready.isDone()) {
            var previousLevel = player.level();
            source.sendSuccess(() -> Component.literal("Loading the Creative world…"), false);
            ready.whenCompleteAsync((loaded, failure) -> {
                if (server.getPlayerList().getPlayer(player.getUUID()) != player || player.isDeadOrDying()
                        || player.level() != previousLevel || !canEnter(player)) {
                    return;
                }
                if (failure != null) {
                    source.sendFailure(Component.literal("The Creative world could not load."));
                    return;
                }
                teleportToCreative(player, loaded);
            }, server);
            return 1;
        }
        return teleportToCreative(player, level);
    }

    private static int teleportToCreative(ServerPlayer player, ServerLevel level) {
        // Worlds can move the original player object before handing off the connection.
        var returnPoint = WorldGroups.isDefault(McWorld.groupOf(player))
            ? new ServerPlayer.SavedPosition(Optional.of(player.level().dimension()), Optional.of(player.position()),
                Optional.of(new Vec2(player.getYRot(), player.getXRot())))
            : ((AttachmentTarget) player).getAttached(SURVIVAL_RETURN);
        var spawn = McWorld.spawnTransition(level, player);
        var onArrival = spawn.postTeleportTransition().then(entity ->
            ((AttachmentTarget) entity).setAttached(SURVIVAL_RETURN, returnPoint));
        player.setPortalCooldown();
        return player.teleport(new TeleportTransition(spawn.newLevel(), spawn.position(), spawn.deltaMovement(),
            spawn.yRot(), spawn.xRot(), spawn.missingRespawnBlock(), spawn.asPassenger(), spawn.relatives(),
            onArrival)) != null ? 1 : 0;
    }

    private static int returnToSurvival(CommandSourceStack source) throws CommandSyntaxException {
        var player = source.getPlayerOrException();
        var saved = ((AttachmentTarget) player).getAttached(SURVIVAL_RETURN);
        if (saved != null && saved.position().isPresent()) {
            var level = saved.dimension().map(source.getServer()::getLevel).orElse(null);
            if (level != null && WorldGroups.isDefault(WorldGroups.groupOrDefault(level))) {
                var rotation = saved.rotation().orElse(Vec2.ZERO);
                player.setPortalCooldown();
                return player.teleport(new TeleportTransition(level, saved.position().orElseThrow(), Vec3.ZERO,
                    rotation.x, rotation.y, TeleportTransition.PLACE_PORTAL_TICKET)) != null ? 1 : 0;
            }
        }
        return travel(source, SURVIVAL);
    }

    private static int travel(CommandSourceStack source, Identifier destination) throws CommandSyntaxException {
        try {
            return McWorld.of(source.getServer()).teleport(source.getPlayerOrException(), destination) ? 1 : 0;
        } catch (WorldsException failure) {
            source.sendFailure(failure.toComponent());
            return 0;
        }
    }
}
