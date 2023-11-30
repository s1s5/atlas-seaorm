use clap::{Parser, Subcommand};
use sea_orm::ActiveValue;
use sea_orm::EntityTrait;
use sea_orm::QueryFilter;
use sea_orm_migration::prelude::*;
use sea_orm_migration::seaql_migrations;
use std::time::SystemTime;
use tracing::info;

#[derive(Parser)]
struct Args {
    #[arg(
        global = true,
        short = 'u',
        long,
        env = "DATABASE_URL",
        help = "Database URL"
    )]
    database_url: Option<String>,

    #[command(subcommand)]
    command: Subcommands,
}

#[derive(Subcommand, PartialEq, Eq, Debug)]
pub enum Subcommands {
    #[command(about = "Apply pending migrations", display_order = 70)]
    Up {
        #[arg(short, long, help = "Number of pending migrations to apply")]
        num: Option<u32>,
    },

    #[command(about = "Rollback applied migrations", display_order = 80)]
    Down {
        #[arg(
            short,
            long,
            default_value = "1",
            help = "Number of applied migrations to be rolled back",
            display_order = 90
        )]
        num: u32,
    },
}

#[async_std::main]
async fn main() -> anyhow::Result<()> {
    let args = Args::parse();
    let db = sea_orm::Database::connect(
        args.database_url
            .or_else(|| std::env::var("DATABASE_URL").ok())
            .unwrap(),
    )
    .await?;

    match args.command {
        Subcommands::Up { num } => exec_up(&db, num).await?,
        Subcommands::Down { num } => exec_down(&db, Some(num)).await?,
    }

    Ok(())
}

type M = migration::Migrator;

async fn exec_up<C>(db: &C, mut steps: Option<u32>) -> Result<(), DbErr>
where
    C: ConnectionTrait,
{
    // let db = manager.get_connection();

    M::install(db).await?;

    if let Some(steps) = steps {
        info!("Applying {} pending migrations", steps);
    } else {
        info!("Applying all pending migrations");
    }

    let migrations = M::get_pending_migrations(db).await?.into_iter();
    if migrations.len() == 0 {
        info!("No pending migrations");
    }
    for migration in migrations {
        if let Some(steps) = steps.as_mut() {
            if steps == &0 {
                break;
            }
            *steps -= 1;
        }
        info!("[dry run] Applying migration '{}'", migration.name());
        // migration.up(manager).await?;
        info!("Migration '{}' has been applied", migration.name());
        let now = SystemTime::now()
            .duration_since(SystemTime::UNIX_EPOCH)
            .expect("SystemTime before UNIX EPOCH!");
        seaql_migrations::Entity::insert(seaql_migrations::ActiveModel {
            version: ActiveValue::Set(migration.name().to_owned()),
            applied_at: ActiveValue::Set(now.as_secs() as i64),
        })
        // .table_name(M::migration_table_name())
        .exec(db)
        .await?;
    }

    Ok(())
}

async fn exec_down<C>(db: &C, mut steps: Option<u32>) -> Result<(), DbErr>
where
    C: ConnectionTrait,
{
    // let db = manager.get_connection();

    M::install(db).await?;

    if let Some(steps) = steps {
        info!("Rolling back {} applied migrations", steps);
    } else {
        info!("Rolling back all applied migrations");
    }

    let migrations = M::get_applied_migrations(db).await?.into_iter().rev();
    if migrations.len() == 0 {
        info!("No applied migrations");
    }
    for migration in migrations {
        if let Some(steps) = steps.as_mut() {
            if steps == &0 {
                break;
            }
            *steps -= 1;
        }
        info!("[dry run] Rolling back migration '{}'", migration.name());
        // migration.down(manager).await?;

        info!("Migration '{}' has been rollbacked", migration.name());
        seaql_migrations::Entity::delete_many()
            .filter(Expr::col(seaql_migrations::Column::Version).eq(migration.name()))
            // .table_name(M::migration_table_name())
            .exec(db)
            .await?;
    }

    Ok(())
}
